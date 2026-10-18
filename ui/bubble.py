"""气泡：圆角浮层，跟随桌宠定位，自动淡出。文本用 QTextDocument 排版，避免换行截断。"""
from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QPropertyAnimation, QRect, QRectF, QTimer, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen,
                           QTextDocument, QTextOption)
from PySide6.QtWidgets import QApplication, QWidget

PAD_X = 14
PAD_Y = 11
TAIL = 11
MAX_W = 300
MIN_W = 158


class Bubble(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
            | Qt.NoDropShadowWindowHint | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self._title = ""
        self._text = ""
        self._accent = QColor("#8FE7FF")
        self._font = QFont("Microsoft YaHei UI", 10)
        self._title_font = QFont("Microsoft YaHei UI", 10)
        self._title_font.setBold(True)

        self._doc = QTextDocument()
        self._doc.setDefaultFont(self._font)
        opt = QTextOption()
        opt.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self._doc.setDefaultTextOption(opt)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.fade_out)

        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setDuration(220)

    # ---------------- 展示 ----------------
    def show_text(self, title: str, text: str, anchor: QRect, seconds: float = 9,
                  accent: str = "#8FE7FF") -> None:
        self._title = title
        self._text = text
        self._accent = QColor(accent)

        tfm = QFontMetrics(self._title_font)
        title_w = tfm.horizontalAdvance(title) if title else 0
        title_h = tfm.height() + 2 if title else 0

        self._doc.setPlainText(text)
        self._doc.setDocumentMargin(0)

        # 先用最大宽度试排，取自然宽度后按最终宽度重排一次
        self._doc.setTextWidth(MAX_W - PAD_X * 2)
        natural = self._doc.idealWidth()
        width = int(min(MAX_W, max(MIN_W, max(natural, title_w) + PAD_X * 2 + 4)))
        inner = width - PAD_X * 2
        self._doc.setTextWidth(inner)
        text_h = math.ceil(self._doc.size().height())

        self.setFixedSize(width, int(text_h + title_h + PAD_Y * 2 + TAIL))
        self._place(anchor)
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        if seconds and seconds > 0:
            self._timer.start(int(seconds * 1000))

    def _place(self, anchor: QRect) -> None:
        screen = QApplication.screenAt(anchor.center()) or QApplication.primaryScreen()
        area = screen.availableGeometry()

        x = anchor.center().x() - self.width() // 2
        y = anchor.top() - self.height() + 6
        if y < area.top():
            y = anchor.bottom() - 6
        x = min(max(x, area.left() + 6), area.right() - self.width() - 6)
        y = min(max(y, area.top() + 6), area.bottom() - self.height() - 6)
        self.move(QPoint(x, y))

    def fade_out(self) -> None:
        self._timer.stop()
        self._anim.stop()
        try:
            self._anim.finished.disconnect(self._after_fade)
        except Exception:
            pass
        self._anim.setStartValue(self.windowOpacity())
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self._after_fade)
        self._anim.start()

    def _after_fade(self) -> None:
        if self.windowOpacity() <= 0.05:
            self.hide()

    # ---------------- 绘制 ----------------
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), Qt.transparent)

        body = QRectF(0, 0, self.width(), self.height() - TAIL)
        path = QPainterPath()
        path.addRoundedRect(body, 14, 14)
        tail = QPainterPath()
        cx = self.width() / 2
        tail.moveTo(cx - 8, body.bottom() - 1)
        tail.lineTo(cx, body.bottom() + TAIL - 1)
        tail.lineTo(cx + 8, body.bottom() - 1)
        tail.closeSubpath()
        path = path.united(tail)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawPath(path.translated(0, 3))

        p.setBrush(QColor(20, 26, 46, 244))
        p.setPen(QPen(QColor(255, 255, 255, 30), 1.2))
        p.drawPath(path)

        p.setPen(QPen(QColor(self._accent.red(), self._accent.green(),
                             self._accent.blue(), 200), 2.2))
        p.drawLine(QPoint(18, 1), QPoint(self.width() - 18, 1))

        y = PAD_Y
        if self._title:
            p.setFont(self._title_font)
            p.setPen(QPen(self._accent))
            fm = QFontMetrics(self._title_font)
            p.drawText(QRect(PAD_X, y, self.width() - PAD_X * 2, fm.height()),
                       Qt.AlignLeft | Qt.AlignVCenter, self._title)
            y += fm.height() + 2

        p.translate(PAD_X, y)
        p.setPen(QPen(QColor("#E8EFFF")))
        self._doc.drawContents(p)
