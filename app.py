"""应用编排：采集线程 → 状态机 → 桌宠/气泡/托盘/面板。"""
from __future__ import annotations

import random
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from core import config, skins
from core.log import log
from core.log import exc as log_exc
from core.store import Store
from monitor.credits import WorkBuddyCredits
from monitor.deepseek import DeepSeekMonitor
from monitor.dsh import DshMonitor
from monitor.workbuddy import WorkBuddyMonitor
from ui.bubble import Bubble
from ui.icons import make_icon, make_icon_from_skin
from ui.panel import Panel
from ui.pet_window import ALERT, DONE, IDLE, WORKING, PetWindow
from ui.sound import Player
from ui.sprite import load_custom_skin, load_skin

ROOT = Path(__file__).resolve().parent
DEDUPE_WINDOW = 45.0  # 同一任务的重复完成提醒合并窗口（秒）

# 摸摸时的随机台词
PAT_LINES = {
    "happy": ["嘿嘿…", "好舒服～", "再来一下嘛", "唔…喜欢"],
    "shy": ["别、别摸了…", "脸要烧起来了", "诶…突然这样"],
    "angry": ["别戳了！", "再点真要生气了", "哼——"],
    "surprise": ["哇啊——", "放我下来！"],
    "sad": ["呜…", "今天有点累"],
}


class Poller(QThread):
    tick = Signal(object)

    def __init__(self, wb, dsh, ds, cr, interval_ms: int):
        super().__init__()
        self.wb, self.dsh, self.ds, self.cr = wb, dsh, ds, cr
        self.interval_ms = interval_ms
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            payload = {}
            try:
                payload["wb"] = self.wb.poll()
            except Exception as exc:
                payload["wb"] = {"ok": False, "error": f"wb: {exc}", "events": [], "tasks": []}
            try:
                payload["dsh"] = self.dsh.poll()
            except Exception as exc:
                payload["dsh"] = {"ok": False, "error": f"dsh: {exc}", "events": [], "active": []}
            try:
                payload["ds"] = self.ds.poll()
            except Exception as exc:
                payload["ds"] = {"ok": False, "error": f"ds: {exc}"}
            try:
                payload["cr"] = self.cr.poll()
            except Exception as exc:
                payload["cr"] = {"ok": False, "error": f"credits: {exc}"}
            self.tick.emit(payload)
            self._stop.wait(self.interval_ms / 1000.0)

    def stop(self) -> None:
        self._stop.set()


class DeskPet(QObject):
    def __init__(self, app: QApplication, parent_pid: int = 0):
        super().__init__()
        self.app = app
        self.parent_pid = parent_pid
        self.cfg = config.load()
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.store = Store(config.DATA_DIR / "ledger.json")

        self.wb = WorkBuddyMonitor(self.store, self.cfg["monitor"]["lookback_minutes"])
        self.dsh = DshMonitor(self.store, self.cfg["monitor"]["lookback_minutes"])
        self.ds = DeepSeekMonitor(
            self.cfg["deepseek"]["refresh_seconds"],
            self.cfg["deepseek"].get("api_key", ""),
            store=self.store,
        )
        self.credits = WorkBuddyCredits(
            self.cfg["credits"]["refresh_seconds"], self.cfg["credits"].get("exe", ""),
            store=self.store,
        )

        self.skin = self._build_skin()

        self.pet = PetWindow(self.cfg["pet"]["scale"], self.skin)
        self.pet.clicked.connect(self._on_pet_clicked)
        self.pet.double_clicked.connect(self._on_pet_double)
        self.pet.drag_started.connect(self._on_drag_started)
        self.pet.drag_finished.connect(self._on_drag_finished)
        self.pet.context_requested.connect(self._show_menu)

        self.bubble = Bubble()
        self.panel = Panel()
        self.panel.set_name(self._pet_name())
        self.sound = Player(
            config.ASSETS_DIR,
            muted=not self.cfg["alerts"]["sound"] or self.cfg["pet"]["muted"],
            custom=self.cfg["alerts"].get("sound_file", ""),
        )

        self._tasks: list[dict] = []
        self._pending: dict[str, dict] = {}
        self._ds_cache: dict = {}
        self._cr_cache: dict = {}
        self._dsh_cache: dict = {}
        self._last_done = ("", 0.0)
        self._last_tick_at = time.time()
        self._pat_times: list[float] = []
        self._last_line = ""
        self._last_pat_at = 0.0
        self._home_pos: QPoint | None = None
        self._alert_centered = False
        self._last_saved_pos = None
        self._icon_idle = make_icon_from_skin(self.skin, "idle") or make_icon("idle")
        self._icon_alert = make_icon_from_skin(self.skin, "alert") or make_icon("alert")

        self._restore_pos()
        self.pet.show()
        self.pet.raise_()

        self._build_tray()
        self.tray.show()

        import os

        log(f"=== 启动 pid={os.getpid()} ppid={os.getppid()} "
            f"skin={'custom' if self.cfg['pet'].get('skin_file') else ('sprite' if self.skin else 'blob')} "
            f"interval={self.cfg['monitor']['interval_ms']}ms ===")

        self.poller = Poller(self.wb, self.dsh, self.ds, self.credits,
                             self.cfg["monitor"]["interval_ms"])
        self.poller.tick.connect(self._on_tick)
        self.poller.start()

        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(2000)
        self._ui_timer.timeout.connect(self._on_ui_tick)
        self._ui_timer.start()

    # ---------------- 位置 ----------------
    def _build_skin(self):
        custom = self.cfg["pet"].get("skin_file") or ""
        if custom:
            p = Path(custom)
            if p.exists():
                skin = load_custom_skin(p)
                if skin:
                    return skin
        if self.cfg["pet"].get("skin", "auto") != "blob":
            skin_id = self.cfg["pet"].get("skin_id") or skins.DEFAULT_ID
            skin = load_skin(skins.frames_dir(skin_id))
            if skin:
                return skin
            return load_skin(skins.frames_dir(skins.DEFAULT_ID))
        return None

    def _restore_pos(self) -> None:
        x, y = self.cfg["pet"].get("x"), self.cfg["pet"].get("y")
        screen = QApplication.primaryScreen().availableGeometry()
        if x is None or y is None:
            self.pet.move(screen.right() - self.pet.width() - 60,
                          screen.bottom() - self.pet.height() - 70)
        else:
            self.pet.move(int(x), int(y))
        self.pet.clamp_to_screen()

    def _persist_pos(self) -> None:
        pos = self.pet.pos()
        if self._last_saved_pos == (pos.x(), pos.y()):
            return
        self._last_saved_pos = (pos.x(), pos.y())
        self.cfg["pet"]["x"] = pos.x()
        self.cfg["pet"]["y"] = pos.y()
        config.save(self.cfg)

    # ---------------- 托盘 ----------------
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self._icon_idle, self)
        self.tray.setToolTip(f"{self._pet_name()} · 任务台")

        menu = QMenu()
        self.act_panel = QAction("打开面板", menu)
        self.act_panel.triggered.connect(self._open_panel)
        menu.addAction(self.act_panel)
        menu.addSeparator()

        self.act_top = QAction("窗口置顶", menu, checkable=True)
        self.act_top.setChecked(bool(self.cfg["pet"]["always_on_top"]))
        self.act_top.triggered.connect(self._toggle_top)
        menu.addAction(self.act_top)

        self.act_mute = QAction("静音", menu, checkable=True)
        self.act_mute.setChecked(bool(self.cfg["pet"]["muted"]))
        self.act_mute.triggered.connect(self._toggle_mute)
        menu.addAction(self.act_mute)

        size_menu = menu.addMenu("大小")
        group = QActionGroup(size_menu)
        for label, val in (("小 80%", 0.8), ("中 100%", 1.0), ("大 125%", 1.25), ("特大 150%", 1.5)):
            act = QAction(label, size_menu, checkable=True)
            act.setChecked(abs(self.cfg["pet"]["scale"] - val) < 0.01)
            act.triggered.connect(lambda _c=False, v=val: self._set_scale(v))
            group.addAction(act)
            size_menu.addAction(act)

        self.act_boot = QAction("开机自启", menu, checkable=True)
        self.act_boot.setChecked(bool(self.cfg.get("autostart")))
        self.act_boot.triggered.connect(self._toggle_autostart)
        menu.addAction(self.act_boot)

        menu.addSeparator()
        act_restart = QAction("重启桌宠", menu)
        act_restart.triggered.connect(self._restart_pet)
        menu.addAction(act_restart)

        act_settings = QAction("设置…", menu)
        act_settings.triggered.connect(self._open_settings)
        menu.addAction(act_settings)

        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(self.quit)
        menu.addAction(act_quit)

        self._menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._open_panel()

    def _toggle_top(self, checked: bool) -> None:
        self.cfg["pet"]["always_on_top"] = checked
        config.save(self.cfg)
        self.pet.set_always_on_top(checked)

    def _toggle_mute(self, checked: bool) -> None:
        self.cfg["pet"]["muted"] = checked
        self.sound.muted = checked or not self.cfg["alerts"]["sound"]
        config.save(self.cfg)

    # ---------------- 设置 ----------------
    def _open_settings(self) -> None:
        from ui.settings import SettingsDialog

        pm = self.skin.frames["idle"] if (self.skin and self.skin.frames) else None
        dlg = SettingsDialog(self.cfg, pm, self.pet)
        dlg.saved.connect(self._apply_settings)
        dlg.exec()

    def _apply_settings(self, cfg: dict) -> None:
        self.cfg = cfg
        config.save(cfg)
        self.sound.muted = not cfg["alerts"]["sound"] or cfg["pet"]["muted"]
        self.sound.set_custom(cfg["alerts"].get("sound_file", ""))
        self.ds.set_key(cfg["deepseek"].get("api_key", ""))

        self._reload_skin()
        self.panel.set_name(self._pet_name())
        self._update_tooltip()

    def _set_scale(self, val: float) -> None:
        self.cfg["pet"]["scale"] = val
        config.save(self.cfg)
        self.pet.set_scale(val)

    def _toggle_autostart(self, checked: bool) -> None:
        ok = set_autostart(checked)
        if ok:
            self.cfg["autostart"] = checked
            config.save(self.cfg)
        else:
            self.act_boot.setChecked(not checked)

    # ---------------- 采集回调 ----------------
    def _on_tick(self, payload: dict) -> None:
        try:
            self._tick(payload)
        except Exception:
            # 槽函数里抛异常会被 Qt 吞掉，桌宠就永远定在上一帧——必须落日志
            log_exc("_on_tick 失败")

    def _tick(self, payload: dict) -> None:
        self._last_tick_at = time.time()
        wb = payload.get("wb") or {}
        dsh = payload.get("dsh") or {}
        self._ds_cache = payload.get("ds") or {}
        self._cr_cache = payload.get("cr") or {}
        self._dsh_cache = payload.get("dsh") or {}

        if wb.get("ok"):
            self._tasks = wb.get("tasks") or []
            self._handle_wb_events(wb.get("events") or [])
        else:
            log(f"wb 采集失败：{wb.get('error', '')[:120]}", "wb_err", 60)

        if dsh.get("ok"):
            self._handle_dsh_events(dsh.get("events") or [])
            for a in self.dsh.pending_alerts():
                self._pending.setdefault(a["approval_id"], a)
        else:
            log(f"dsh 采集失败：{dsh.get('error', '')[:120]}", "dsh_err", 60)

        self._refresh_state()
        if self.panel.isVisible():
            self.panel.update_data(self._panel_data())
        self._update_tooltip()

    def _handle_wb_events(self, events: list[dict]) -> None:
        changed = False
        for ev in events:
            kind = ev.get("kind")
            title = (ev.get("title") or "未命名任务").strip()
            key = f"wb:{ev.get('sid')}:{kind}:{int(ev.get('ts') or 0)}"
            if kind in ("session_completed", "session_error", "session_stopped"):
                if not self.store.should_fire(key):
                    continue
                changed = True
                if kind == "session_completed":
                    self._notify_done(title, ev.get("cwd", ""), source="WorkBuddy")
                elif kind == "session_error":
                    self._notify_error(title, ev.get("cwd", ""))
                else:
                    self.store.push_history("stop", f"中止：{title}")
            elif kind == "session_started":
                self.store.push_history("start", f"开始：{title}")
                self.pet.set_state(WORKING)
                changed = True
        if changed:
            self.store.save()

    def _handle_dsh_events(self, events: list[dict]) -> None:
        changed = False
        for ev in events:
            kind = ev.get("kind")
            title = (ev.get("title") or "当前会话").strip()
            if kind == "approval":
                aid = ev.get("approval_id") or ""
                if not aid:
                    continue
                key = f"approval:{aid}"
                if not self.store.should_fire(key):
                    continue
                changed = True
                self._notify_approval(ev)
            elif kind == "approval_cleared":
                self._pending.pop(ev.get("approval_id") or "", None)
                if not self._pending:
                    self._clear_alert()
            elif kind == "turn_end":
                reason = ev.get("reason")
                if reason == "completed":
                    self._notify_done(title, ev.get("cwd", ""), source="会话")
                elif reason in ("error", "failed"):
                    self._notify_error(title, ev.get("cwd", ""))
            elif kind == "turn_start":
                if self.pet.state != ALERT:
                    self.pet.set_state(WORKING)
        if changed:
            self.store.save()

    # ---------------- 提醒 ----------------
    def _notify_done(self, title: str, cwd: str, source: str = "") -> None:
        now = time.time()
        if title == self._last_done[0] and now - self._last_done[1] < DEDUPE_WINDOW:
            return
        self._last_done = (title, now)
        self.store.push_history("done", f"完成：{title}")
        if not self.cfg["alerts"]["complete"]:
            return
        self.pet.set_state(DONE)
        self._show_bubble("✅ 任务完成", f"{title}\n{cwd}", accent="#6FE7B7")
        self.sound.play("complete")
        self._tray_message("任务完成", f"{title}\n{cwd}" if cwd else title)

    def _notify_error(self, title: str, cwd: str) -> None:
        self.store.push_history("error", f"出错：{title}")
        if not self.cfg["alerts"]["complete"]:
            return
        self.pet.set_state(DONE)
        self._show_bubble("⚠️ 任务中断", f"{title}\n{cwd}", accent="#FFB86B")
        self.sound.play("error")
        self._tray_message("任务中断", title)

    def _notify_approval(self, ev: dict) -> None:
        aid = ev.get("approval_id") or ""
        self._pending[aid] = ev
        tool = ev.get("tool") or "操作"
        reason = (ev.get("reason") or "").strip()
        if len(reason) > 200:
            reason = reason[:200] + "…"
        title = (ev.get("title") or "当前会话").strip()
        self.store.push_history("approval", f"待确认：{tool}")

        if not self.cfg["alerts"]["approval"]:
            return

        self.pet.set_state(ALERT)
        delay = 0
        if self.cfg["alerts"]["center_on_alert"] and not self._alert_centered:
            self._home_pos = self.pet.pos()
            self.pet.animate_to(self.pet.center_target())
            self._alert_centered = True
            delay = 460   # 等移动动画结束再定位气泡，否则会飘在旧位置

        body = f"{title}\n\n{reason}" if reason else title

        def _bubble() -> None:
            self._show_bubble(f"需要你确认 · {tool}", body, accent="#FF8A78", seconds=0)

        if delay:
            QTimer.singleShot(delay, _bubble)
        else:
            _bubble()
        self.sound.play("alert")
        self._tray_message("需要你确认", f"{tool} · {title}")

    def _clear_alert(self) -> None:
        self.bubble.fade_out()
        self._alert_centered = False
        if self._home_pos is not None:
            self.pet.animate_to(self._home_pos, 380)
            self._home_pos = None
        running = any(t.get("status") == "working" for t in self._tasks)
        self.pet.set_state(WORKING if running else IDLE)

    def _show_bubble(self, title: str, text: str, accent: str = "#8FE7FF",
                     seconds: float | None = None) -> None:
        if seconds is None:
            seconds = float(self.cfg["alerts"]["bubble_seconds"])
        self.bubble.show_text(title, text, self.pet.geometry(), seconds, accent)

    def _tray_message(self, title: str, body: str) -> None:
        if not self.cfg["alerts"]["tray"]:
            return
        try:
            self.tray.showMessage(title, body[:180], QSystemTrayIcon.Information, 6000)
        except Exception:
            pass

    # ---------------- 状态 ----------------
    def _refresh_state(self) -> None:
        if self.pet.state == ALERT:
            # 没有待确认项还挂着 ALERT，超过 60 秒就放下来，别卡死
            if not self._pending and time.time() - self.pet._alert_at > 60:
                log("ALERT 超时自动复位")
                self.pet.set_state(WORKING if self._running_count() else IDLE)
            return
        if self.pet.state == DONE and self.pet._t - self.pet._jump_t0 < 2.4:
            return
        running = self._running_count()
        if running:
            if self.pet.state != WORKING:
                log(f"状态 -> working（运行中 {running}）")
            self.pet.set_state(WORKING)
        elif self.pet.state == WORKING:
            log("状态 -> idle")
            self.pet.set_state(IDLE)

    def _running_count(self) -> int:
        return sum(1 for t in self._tasks if t.get("status") == "working")

    def _pet_name(self) -> str:
        return (self.cfg["pet"].get("name") or "").strip() or "墨团"

    def _update_tooltip(self) -> None:
        running = sum(1 for t in self._tasks if t.get("status") == "working")
        parts = []
        cr = self._cr_cache or {}
        if cr.get("ok") and isinstance(cr.get("remaining"), int):
            parts.append(f"剩余 {cr['remaining']} 积分")
        used_today = cr.get("used_today") if cr.get("ok") else None
        if isinstance(used_today, (int, float)) and used_today > 0:
            parts.append(f"今日 −{int(used_today)}")
        else:
            parts.append(f"今日 {self.store.credits_today():.0f}")
        ds = self._ds_cache or {}
        if ds.get("ok") and isinstance(ds.get("balance"), (int, float)):
            sym = "¥" if ds.get("currency") in (None, "", "CNY") else "$"
            parts.append(f"{sym}{ds['balance']:.2f}")
        parts.append(f"运行中 {running}")
        if self._pending:
            parts.append(f"待确认 {len(self._pending)}")
        self.tray.setToolTip(f"{self._pet_name()} · " + " · ".join(parts))
        self.tray.setIcon(self._icon_alert if self._pending else self._icon_idle)

    # ---------------- 面板 ----------------
    def _panel_data(self) -> dict:
        ds = self._ds_cache or {}
        running = [t for t in self._tasks if t.get("status") == "working"]
        running.sort(key=lambda t: -(t.get("updated_at") or 0))
        return {
            "credits_today": self.store.credits_today(),
            "credits_total": self.store.credits_total(),
            "credits_week": self.store.credits_by_day(7),
            "wb_credits": self._cr_cache,
            "dsh": self._dsh_cache.get("active") or [],
            "deepseek": ds,
            "running": running,
            "pending": list(self._pending.values()),
            "history": self.store.recent_history(4),
        }

    def _open_panel(self) -> None:
        self.credits.request_refresh()
        if self.bubble.isVisible():
            self.bubble.hide()      # 气泡和面板会重叠，开面板时收起气泡
        self.panel.update_data(self._panel_data())
        self.panel.place_near(self.pet.geometry())
        self.panel.show()
        self.panel.raise_()

    def _on_pet_clicked(self) -> None:
        # 有待确认时，点一下就是"我看过了"
        if self._pending:
            n = len(self._pending)
            self._pending.clear()
            self.store.push_history("ack", f"已查看 {n} 条待确认")
            self.store.save()
            self._clear_alert()
            self.pet.set_mood("happy", 1.8)
            return

        now = time.time()
        if now - self._last_pat_at < 0.35:
            return                      # 连点太快时丢弃，避免台词刷屏
        self._last_pat_at = now
        self._pat_times = [t for t in self._pat_times if now - t < 3.0]
        self._pat_times.append(now)
        if len(self._pat_times) >= 5:
            self._pat_times.clear()
            mood = "angry"
        else:
            mood = random.choice(("happy", "happy", "shy", "happy"))

        self.pet.set_mood(mood, 2.6)
        self.sound.play("click")
        pool = PAT_LINES.get(mood, ["…"])
        fresh = [l for l in pool if l != self._last_line] or pool
        line = random.choice(fresh)
        self._last_line = line
        self.bubble.show_text("", line, self.pet.geometry(), seconds=2.0)
        log(f"摸摸 -> {mood}")

    def _on_pet_double(self) -> None:
        self.pet.set_mood(None)
        if self.panel.isVisible():
            self.panel.hide()
        else:
            self._open_panel()

    def _on_drag_started(self) -> None:
        self.pet.set_mood("surprise", 1.6)

    def _on_drag_finished(self) -> None:
        self.pet.set_mood(None)

    def _show_menu(self, global_pos: QPoint) -> None:
        self._menu.popup(global_pos)

    def _on_ui_tick(self) -> None:
        self._persist_pos()
        self._check_poller_health()
        if self.panel.isVisible():
            self.panel.update_data(self._panel_data())

    def _check_poller_health(self) -> None:
        """采集线程静默超过 20 秒就重建——宁可多一次重启，也不要永远定在 idle。"""
        if not self._last_tick_at:
            return
        gap = time.time() - self._last_tick_at
        if gap < 20:
            return
        log(f"采集线程 {int(gap)} 秒无心跳，重建")
        try:
            self.poller.stop()
            self.poller.wait(2000)
        except Exception:
            log_exc("停止旧采集线程失败")
        try:
            self.poller = Poller(self.wb, self.dsh, self.ds, self.credits,
                                 self.cfg["monitor"]["interval_ms"])
            self.poller.tick.connect(self._on_tick)
            self.poller.start()
        except Exception:
            log_exc("重建采集线程失败")
        self._last_tick_at = time.time()

    # ---------------- 换肤 ----------------
    def _switch_skin(self, skin_id: str) -> None:
        if skin_id == (self.cfg["pet"].get("skin_id") or skins.DEFAULT_ID):
            return
        self.cfg["pet"]["skin_id"] = skin_id
        self.cfg["pet"]["skin_file"] = ""
        config.save(self.cfg)
        self._reload_skin()
        name = next((s["name"] for s in skins.available() if s["id"] == skin_id), skin_id)
        log(f"切换皮肤 -> {skin_id}")
        self._show_bubble_once(f"换上 {name} 了", "外观")

    def _show_bubble_once(self, text: str, title: str = "") -> None:
        self.bubble.show_text(title or "", text, self.pet.geometry(), seconds=3.0)

    def _reload_skin(self) -> None:
        self.skin = self._build_skin()
        self.pet.skin = self.skin
        self.pet._apply_size()
        self.pet.clamp_to_screen()
        self.pet.update()
        self._icon_idle = make_icon_from_skin(self.skin, "idle") or make_icon("idle")
        self._icon_alert = make_icon_from_skin(self.skin, "alert") or make_icon("alert")
        self.tray.setIcon(self._icon_idle)

    # ---------------- 重启 ----------------
    def _restart_pet(self) -> None:
        """延迟 1.5 秒再拉起自己：先让当前进程释放单实例锁。"""
        import json
        import subprocess
        import sys

        args = [str(ROOT / "main.py")]
        if self.parent_pid:
            args += ["--parent-pid", str(self.parent_pid)]
        code = (
            "import subprocess,sys,time;time.sleep(1.5);"
            f"subprocess.Popen({json.dumps([sys.executable] + args)},"
            f"cwd={json.dumps(str(ROOT))},creationflags=0x00000008)"
        )
        try:
            subprocess.Popen([sys.executable, "-c", code],
                             creationflags=0x00000008, close_fds=True)
        except Exception:
            log_exc("重启失败")
        log("收到重启请求")
        self.quit()

    # ---------------- 退出 ----------------
    def quit(self) -> None:
        try:
            self.poller.stop()
            if not self.poller.wait(3000):
                self.poller.terminate()
                self.poller.wait(500)
        except Exception:
            pass
        self._persist_pos()
        self.store.save()
        self.tray.hide()
        self.app.quit()


# ---------------- 开机自启 ----------------
def set_autostart(enable: bool) -> bool:
    import sys

    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
        name = "WorkBuddyDeskPet"
        if enable:
            exe = Path(sys.executable)
            pyw = exe.with_name("pythonw.exe")
            runner = pyw if pyw.exists() else exe
            cmd = f'"{runner}" "{ROOT / "main.py"}"'
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception:
        return False
