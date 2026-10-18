"""气泡：圆角浮层，跟随桌宠定位，自动淡出。文本用 QTextDocument 排版，避免换行截断。"""
from __future__ import annotations

import math

from pathlib import Path

from PySide6.QtCore import QPoint, QPropertyAnimation, QRect, QRectF, QTimer, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QPainter, QPixmap,
                           QTextCharFormat, QTextCursor, QTextDocument, QTextOption)
from PySide6.QtWidgets import QApplication, QWidget

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "bubble"
PAD_X = 30          # 留出毛绒边框
PAD_Y = 20
TAIL = 0            # 毛绒面板没有尖角，气泡直接浮在头顶
MAX_W = 320
MIN_W = 172
TEXT = "#3B3644"    # 白底上的深色字

_FUZZ: QPixmap | None = None


def _fuzz() -> QPixmap:
    """毛绒底图（Krea2 生成，tools/make_bubble_art.py）。"""
    global _FUZZ
    if _FUZZ is None:
        p = ASSETS / "fluff.png"
        _FUZZ = QPixmap(str(p)) if p.exists() else QPixmap()
    return _FUZZ


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
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(TEXT))
        cur = QTextCursor(self._doc)
        cur.select(QTextCursor.Document)
        cur.mergeCharFormat(fmt)

        # 先用最大宽度试排，取自然宽度后按最终宽度重排一次
        self._doc.setTextWidth(MAX_W - PAD_X * 2)
        natural = self._doc.idealWidth()
        width = int(min(MAX_W, max(MIN_W, max(natural, title_w) + PAD_X * 2 + 4)))
        inner = width - PAD_X * 2
        self._doc.setTextWidth(inner)
        text_h = math.ceil(self._doc.size().height())

        self.setFixedSize(width, int(text_h + title_h + PAD_Y * 2))
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
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.fillRect(self.rect(), Qt.transparent)

        body = QRectF(0.8, 0.8, self.width() - 1.6, self.height() - 1.6)
        radius = min(18.0, body.height() / 2.0)

        # 1) 实底：保证文字有干净的背景
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(252, 251, 252, 246))
        p.drawRoundedRect(body, radius, radius)

        # 2) 毛绒纹理：压低透明度叠在实底上，只当质感，不抢字
        pm = _fuzz()
        if not pm.isNull():
            p.setOpacity(0.38)
            self._draw_nine(p, pm, body)
            p.setOpacity(1.0)

        # 3) 边缘一圈淡描边，把面板和桌面分开
        p.setBrush(Qt.NoBrush)
        p.setPen(QColor(210, 206, 216, 170))
        p.drawRoundedRect(body, radius, radius)

        y = PAD_Y - 4
        if self._title:
            p.setFont(self._title_font)
            p.setPen(QColor(self._accent.darker(205)))
            fm = QFontMetrics(self._title_font)
            p.drawText(QRect(PAD_X, y, self.width() - PAD_X * 2, fm.height()),
                       Qt.AlignLeft | Qt.AlignVCenter, self._title)
            y += fm.height() + 2

        p.translate(PAD_X, y)
        self._doc.drawContents(p)

    @staticmethod
    def _draw_nine(p: QPainter, pm: QPixmap, rect: QRectF) -> None:
        """九宫格：四角保留绒毛细节，边和中间拉伸；目标角固定 22px，不被源图尺寸带偏。"""
        sw, sh = pm.width(), pm.height()
        src = min(sw, sh) * 0.30
        dst = min(22.0, rect.width() / 3.0, rect.height() / 3.0)
        sx = (0.0, src, sw - src, float(sw))
        sy = (0.0, src, sh - src, float(sh))
        dx = (rect.left(), rect.left() + dst, rect.right() - dst, rect.right())
        dy = (rect.top(), rect.top() + dst, rect.bottom() - dst, rect.bottom())
        for i in range(3):
            for j in range(3):
                w = dx[i + 1] - dx[i]
                h = dy[j + 1] - dy[j]
                if w <= 0 or h <= 0:
                    continue
                p.drawPixmap(QRectF(dx[i], dy[j], w, h),
                             pm, QRectF(sx[i], sy[j], sx[i + 1] - sx[i], sy[j + 1] - sy[j]))
