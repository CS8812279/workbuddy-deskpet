"""入口：python main.py [--selftest|--check]"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run_check() -> int:
    """不开窗口，跑一轮采集并打印结果，用于排查数据源。"""
    import json

    from core import config
    from core.store import Store
    from monitor.credits import WorkBuddyCredits
    from monitor.deepseek import DeepSeekMonitor
    from monitor.dsh import DshMonitor
    from monitor.workbuddy import WorkBuddyMonitor

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    store = Store(config.DATA_DIR / "ledger.json")
    cfg = config.load()
    wb = WorkBuddyMonitor(store, 30)
    dsh = DshMonitor(store, 30)
    ds = DeepSeekMonitor(1)
    cr = WorkBuddyCredits(cfg["credits"]["refresh_seconds"], cfg["credits"].get("exe", ""))

    r1 = wb.poll()
    r2 = dsh.poll()
    r3 = ds.poll(force=True)
    r4 = cr.poll(force=True)
    summary = {
        "workbuddy": {
            "ok": r1["ok"], "error": r1.get("error", ""),
            "tasks": len(r1.get("tasks") or []),
            "running": [t["title"] for t in (r1.get("tasks") or []) if t["status"] == "working"],
        },
        "dsh": {
            "ok": r2["ok"], "error": r2.get("error", ""),
            "active": r2.get("active"),
            "events": len(r2.get("events") or []),
        },
        "deepseek": r3,
        "wb_credits": r4,
        "credits_today": round(store.credits_today(), 2),
        "credits_total": round(store.credits_total(), 1),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def run_selftest() -> int:
    """渲染各状态静帧，人工核对造型。"""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtWidgets import QApplication

    from ui.character import draw_pet

    app = QApplication(sys.argv)
    out = ROOT / "assets" / "preview"
    out.mkdir(parents=True, exist_ok=True)

    for state in ("idle", "working", "done", "alert", "sleep"):
        pm = QPixmap(360, 360)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        draw_pet(
            p, 360, 360, state, 1.1,
            blink=1.0,
            jump=-22 if state == "done" else 0.0,
            alert=1.0 if state == "alert" else 0.0,
        )
        p.end()
        pm.save(str(out / f"state_{state}.png"))

    from ui.bubble import Bubble
    from ui.icons import make_pixmap
    from ui.panel import Panel

    bubble = Bubble()
    from PySide6.QtCore import QRect

    bubble.show_text(
        "需要你确认 · pwsh",
        "escalate sandbox to danger-full-access：工作区的 Windows 文件权限挡住了所有命令，"
        "这个脚本会补上当前登录用户的完全控制项。",
        QRect(400, 400, 200, 200), 0, "#FF8A78",
    )
    bubble.grab().save(str(out / "bubble.png"))

    panel = Panel()
    from PySide6.QtCore import QPoint

    panel.move(QPoint(0, 0))
    panel.show()
    panel.update_data({
        "credits_today": 3.06,
        "credits_total": 128.4,
        "wb_credits": {"ok": True, "remaining": 2622, "packages": 21, "expiring": "11-15"},
        "credits_week": [("2026-10-12", 1.2), ("2026-10-13", 21.0), ("2026-10-14", 3.8),
                         ("2026-10-15", 0.0), ("2026-10-16", 1.0), ("2026-10-17", 6.1),
                         ("2026-10-18", 3.06)],
        "deepseek": {"ok": True, "balance": 113.71, "today": 3.06},
        "running": [{"title": "开发任务监控桌宠软件", "updated_at": 0}],
        "pending": [{"tool": "pwsh", "title": "开发任务监控桌宠软件"}],
        "history": [{"kind": "done", "text": "完成：生成四版游戏策划案", "at": 0}],
    })
    panel.grab().save(str(out / "panel.png"))

    make_pixmap(128).save(str(out / "icon.png"))
    print("preview dir:", out)
    app.quit()
    return 0


def run_demo() -> int:
    """实机演示：弹一次「待确认」并截屏，用于验证真机合成效果。"""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    from app import DeskPet

    pet = DeskPet(app, parent_pid)

    def fire() -> None:
        pet._notify_approval({
            "approval_id": "demo-1",
            "tool": "命令执行",
            "title": "开发任务监控桌宠软件",
            "cwd": "D:/AI Work",
            "reason": "需要在沙箱外执行：读取工作区目录权限，并为当前登录用户补全控制项。",
        })

    def shot() -> None:
        scr = QApplication.primaryScreen()
        if scr:
            scr.grabWindow(0).save(str(ROOT / "assets" / "preview" / "screen.png"))
        pet.panel.update_data(pet._panel_data())
        pet.panel.place_near(pet.pet.geometry())
        pet.panel.show()
        QTimer.singleShot(600, shot2)

    def shot2() -> None:
        scr = QApplication.primaryScreen()
        if scr:
            scr.grabWindow(0).save(str(ROOT / "assets" / "preview" / "screen_panel.png"))
        pet.quit()
        QTimer.singleShot(300, lambda: __import__("os")._exit(0))

    QTimer.singleShot(1500, fire)
    QTimer.singleShot(4200, shot)
    return app.exec()


_INSTANCE_LOCK = None


def _acquire_single_instance():
    """单实例：锁住临时目录里文件的一个字节。

    用 msvcrt.locking 而不是 QLockFile / 命名互斥体：
    - QLockFile 被强杀后会留下僵尸锁文件，桌宠再也起不来；
    - 命名互斥体在句柄被其它进程继承时会误判（实测踩到）。
    文件锁由内核按句柄持有，进程一死立刻释放，且新进程重新打开同一路径即可重试。
    """
    global _INSTANCE_LOCK
    if sys.platform != "win32":
        return True
    import msvcrt
    import tempfile

    path = Path(tempfile.gettempdir()) / "workbuddy-deskpet.lock"
    try:
        fh = open(path, "a+b")
    except OSError:
        return True          # 打不开锁文件就别拦着用户用
    try:
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        fh.close()
        return False
    _INSTANCE_LOCK = fh      # 保持句柄，进程活着锁就在
    return True


def main() -> int:
    if "--check" in sys.argv:
        return run_check()
    if "--selftest" in sys.argv:
        return run_selftest()
    if "--demo" in sys.argv:
        return run_demo()

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("WorkBuddyDeskPet")

    if not _acquire_single_instance():
        print("桌宠已在运行")
        return 0

    from app import DeskPet

    parent_pid = 0
    if "--parent-pid" in sys.argv:
        idx = sys.argv.index("--parent-pid")
        if idx + 1 < len(sys.argv):
            try:
                parent_pid = int(sys.argv[idx + 1])
            except ValueError:
                parent_pid = 0

    pet = DeskPet(app, parent_pid)
    if parent_pid > 0:
        # 由 DSH 插件拉起时，宿主没了就自杀，避免残留进程
        from core.guard import watch

        watch(parent_pid, pet.quit)
    rc = app.exec()
    return rc


if __name__ == "__main__":
    sys.exit(main())
