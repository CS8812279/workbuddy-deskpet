"""信息面板：今日积分、余额、运行中任务、待确认。"""
from __future__ import annotations

import time
from datetime import datetime

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget)

ACCENT = "#7FB2FF"
WARN = "#FF8A78"
OK = "#6FE7B7"
DIM = "#8A97B8"


class SparkBars(QWidget):
    """近 7 日积分迷你柱状图。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self.values: list[tuple[str, float]] = []

    def set_values(self, values: list[tuple[str, float]]) -> None:
        self.values = values
        self.update()

    def paintEvent(self, _e) -> None:
        if not self.values:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        top = max(v for _, v in self.values) or 1.0
        n = len(self.values)
        gap = 6
        inset = 6
        usable = self.width() - inset * 2
        w = (usable - gap * (n - 1)) / n
        base = self.height() - 17
        for i, (_day, v) in enumerate(self.values):
            h = max(2.0, (v / top) * (base - 6))
            x = inset + i * (w + gap)
            r = QRectF(x, base - h, w, h)
            is_today = i == n - 1
            col = QColor("#5B8CFF" if not is_today else "#9FC2FF")
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(r, 2.5, 2.5)
            p.setPen(QPen(QColor(DIM) if not is_today else QColor("#D6E6FF")))
            f = p.font()
            f.setPointSizeF(7.0)
            f.setBold(is_today)
            p.setFont(f)
            label = str(int(_day[8:10]))
            p.drawText(QRectF(x - 3, base + 2, w + 6, 15), Qt.AlignHCenter | Qt.AlignTop, label)


def _section(text: str, color: str = DIM) -> QLabel:
    lab = QLabel(text)
    lab.setStyleSheet(
        f"color:{color}; font-size:11px; letter-spacing:1px; font-weight:600;"
    )
    return lab


def _item(text: str, color: str = "#DCE6FF", size: int = 12) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setStyleSheet(f"color:{color}; font-size:{size}px;")
    return lab


class Panel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(336, 400)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(9)

        # 顶部
        head = QHBoxLayout()
        head.setSpacing(8)
        self.title = QLabel("墨团 · 任务台")
        self.title.setStyleSheet("color:#EAF1FF; font-size:14px; font-weight:600;")
        self.clock = QLabel("")
        self.clock.setStyleSheet(f"color:{DIM}; font-size:11px;")
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(self.clock)
        root.addLayout(head)

        # 两个 KPI
        kpi = QHBoxLayout()
        kpi.setSpacing(10)
        self.kpi_credit = QFrame()
        self.kpi_credit.setObjectName("kpi")
        self.kpi_ds = QFrame()
        self.kpi_ds.setObjectName("kpi")
        for box in (self.kpi_credit, self.kpi_ds):
            lay = QVBoxLayout(box)
            lay.setContentsMargins(12, 9, 12, 9)
            lay.setSpacing(2)
            box._cap = QLabel("")
            box._cap.setStyleSheet(f"color:{DIM}; font-size:10px;")
            box._val = QLabel("--")
            box._val.setStyleSheet("color:#F2F6FF; font-size:19px; font-weight:600;")
            box._sub = QLabel("")
            box._sub.setStyleSheet(f"color:{DIM}; font-size:10px;")
            lay.addWidget(box._cap)
            lay.addWidget(box._val)
            lay.addWidget(box._sub)
        self.kpi_credit._cap.setText("WORKBUDDY 积分")
        self.kpi_ds._cap.setText("DEEPSEEK 余额")
        kpi.addWidget(self.kpi_credit, 1)
        kpi.addWidget(self.kpi_ds, 1)
        root.addLayout(kpi)

        self.spark = SparkBars()
        root.addWidget(self.spark)

        self.lbl_running = _section("运行中")
        root.addWidget(self.lbl_running)
        self.box_running = _item("—")
        root.addWidget(self.box_running)

        self.lbl_dsh = _section("DSH 会话")
        root.addWidget(self.lbl_dsh)
        self.box_dsh = _item("—")
        root.addWidget(self.box_dsh)

        self.lbl_pending = _section("待你确认", WARN)
        root.addWidget(self.lbl_pending)
        self.box_pending = _item("暂无", DIM)
        root.addWidget(self.box_pending)

        self.lbl_recent = _section("最近")
        root.addWidget(self.lbl_recent)
        self.box_recent = _item("—", "#B7C4E4", 11)
        root.addWidget(self.box_recent)

        root.addStretch(1)
        foot = QLabel("右键桌宠可缩放 · 静音 · 退出")
        foot.setStyleSheet(f"color:{DIM}; font-size:10px;")
        root.addWidget(foot)

        self.setStyleSheet(
            "QFrame#kpi{background:rgba(255,255,255,10);"
            "border:1px solid rgba(255,255,255,18); border-radius:11px;}"
        )

    # ---------------- 数据 ----------------
    def set_name(self, name: str) -> None:
        self.title.setText(f"{name} · 任务台")

    def update_data(self, st: dict) -> None:
        self.clock.setText(datetime.now().strftime("%H:%M"))

        cr = st.get("wb_credits") or {}
        today = st.get("credits_today", 0)
        if cr.get("ok"):
            remain = cr.get("remaining")
            self.kpi_credit._val.setText(f"{remain:,}" if isinstance(remain, int) else "--")
            used_today = cr.get("used_today")
            self.kpi_credit._sub.setText(
                f"今日 −{int(used_today)}" if isinstance(used_today, (int, float)) and used_today
                else "今日暂未消耗"
            )
            self.kpi_credit.setToolTip(
                f"共 {cr.get('packages', 0)} 个套餐包"
                + (f"，最近 {cr['expiring']} 到期" if cr.get("expiring") else "")
            )
        else:
            self.kpi_credit._val.setText("--")
            self.kpi_credit._sub.setText((cr.get("error") or "未连接")[:16])
            self.kpi_credit.setToolTip(cr.get("error") or "")

        ds = st.get("deepseek") or {}
        if ds.get("ok"):
            bal = ds.get("balance")
            sym = "¥" if ds.get("currency") in (None, "", "CNY") else "$"
            self.kpi_ds._val.setText(f"{sym}{bal:.2f}" if isinstance(bal, (int, float)) else "--")
            today = ds.get("today")
            self.kpi_ds._sub.setText(
                f"今日 {sym}{today:.2f}" if isinstance(today, (int, float)) else "今日 --"
            )
            self.kpi_ds.setToolTip(f"数据来源：{ds.get('source') or '未知'}")
        else:
            self.kpi_ds._val.setText("--")
            self.kpi_ds._sub.setText(ds.get("error", "未连接")[:18])
            self.kpi_ds.setToolTip(ds.get("error") or "")

        self.spark.set_values(st.get("credits_week") or [])

        running = st.get("running") or []
        self.lbl_running.setText(f"运行中  {len(running)}")
        if running:
            lines = []
            for t in running[:4]:
                raw = t.get("updated_at") or 0
                secs = max(0, int(time.time() - raw / 1000)) if raw else 0
                ago = f"{_dur(secs)}前" if raw else "刚刚"
                lines.append(
                    f"· {t.get('title', '')[:22]}  "
                    f"<span style='color:{DIM}'>{ago}</span>"
                )
            self.box_running.setText("<br>".join(lines))
            self.box_running.setStyleSheet(f"color:{OK}; font-size:12px;")
        else:
            self.box_running.setText("没有正在跑的任务")
            self.box_running.setStyleSheet(f"color:{DIM}; font-size:12px;")

        dsh = st.get("dsh") or []
        self.lbl_dsh.setText(f"DSH 会话  {len(dsh)}")
        if dsh:
            lines = []
            act = (dsh[0] or {}).get("activity")
            if act:
                icon = "✎" if act.get("kind") == "tool" else "…"
                lines.append(
                    f"<span style='color:{ACCENT}'>{icon} {act.get('text','')[:24]}</span>"
                )
            for s in dsh[:3]:
                idle = float(s.get("idle_min", 999))
                live = idle < 3
                dot = "●" if live else "○"
                color = OK if live else DIM
                lines.append(
                    f"<span style='color:{color}'>{dot}</span> "
                    f"{(s.get('title') or '会话')[:20]}  "
                    f"<span style='color:{DIM}'>{_idle(idle)}</span>"
                )
            self.box_dsh.setText("<br>".join(lines))
            self.box_dsh.setStyleSheet("color:#DCE6FF; font-size:12px;")
        else:
            self.box_dsh.setText("未发现活跃会话")
            self.box_dsh.setStyleSheet(f"color:{DIM}; font-size:12px;")

        pending = st.get("pending") or []
        self.lbl_pending.setText(f"待你确认  {len(pending)}")
        if pending:
            lines = []
            for a in pending[:3]:
                tool = a.get("tool") or "操作"
                title = (a.get("title") or "")[:18]
                lines.append(f"· <b>{tool}</b>  {title}")
            self.box_pending.setText("<br>".join(lines))
            self.box_pending.setStyleSheet(f"color:{WARN}; font-size:12px;")
        else:
            self.box_pending.setText("暂无")
            self.box_pending.setStyleSheet(f"color:{DIM}; font-size:12px;")

        hist = st.get("history") or []
        if hist:
            lines = []
            for h in hist[:3]:
                t = datetime.fromtimestamp(h.get("at", 0)).strftime("%H:%M")
                lines.append(
                    f"<span style='color:{DIM}'>{t}</span>  {h.get('text', '')[:26]}"
                )
            self.box_recent.setText("<br>".join(lines))

        self.adjustSize()

    # ---------------- 绘制 ----------------
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        body = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 80))
        p.drawRoundedRect(body.translated(0, 4), 16, 16)
        p.setBrush(QColor(16, 22, 42, 248))
        p.setPen(QPen(QColor(126, 158, 240, 70), 1.2))
        p.drawRoundedRect(body, 16, 16)

    def place_near(self, anchor) -> None:
        from PySide6.QtWidgets import QApplication

        screen = QApplication.screenAt(anchor.center()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        self.adjustSize()
        w, h = self.width(), self.height()
        x = anchor.right() + 10
        if x + w > area.right():
            x = anchor.left() - w - 10
        y = anchor.center().y() - h // 2
        x = min(max(x, area.left() + 8), area.right() - w - 8)
        y = min(max(y, area.top() + 8), area.bottom() - h - 8)
        self.move(x, y)


def _idle(minutes: float) -> str:
    if minutes < 1:
        return "刚刚"
    if minutes < 60:
        return f"{int(minutes)} 分钟前"
    return f"{int(minutes // 60)} 小时前"


def _dur(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}秒"
    if seconds < 3600:
        return f"{seconds // 60}分"
    return f"{seconds // 3600}小时"
