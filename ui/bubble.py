"""气泡：圆角浮层，跟随桌宠定位，自动淡出。文本用 QTextDocument 排版，避免换行截断。"""
from __future__ import annotations

import math

from pathlib import Path

from PySide6.QtCore import (QPoint, QPointF, QPropertyAnimation, QRect, QRectF,
                            QTimer, Qt)
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QPainter, QPixmap,
                           QRadialGradient, QTextCharFormat, QTextCursor,
                           QTextDocument, QTextOption)
from PySide6.QtWidgets import QApplication, QWidget

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "bubble"
PAD_X = 38          # 留出毛绒边框
PAD_Y = 26
TAIL = 0            # 毛绒面板没有尖角，气泡直接浮在头顶
MAX_W = 320
MIN_W = 172
TEXT = "#3B3644"    # 白底上的深色字

_FUZZ: QPixmap | None = None
def _fuzz() -> QPixmap:
    """白色毛绒面板，已抠图（Krea2 出图 + birefnet 抠图，见 tools/make_bubble_art.py）。

    直接整张铺进气泡，轮廓就是它自己的毛边——不裁圆角、不描边。
    """
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

        self._family = "Microsoft YaHei UI"
        self._size = 10
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

    def set_style(self, family: str, size: int) -> None:
        """字体可换——字体族与字号都来自 config，用户改了立即生效。"""
        self._family = family or "Microsoft YaHei UI"
        self._size = max(7, min(24, int(size)))
        self._font = QFont(self._family, self._size)
        self._doc.setDefaultFont(self._font)
        self._title_font = QFont(self._family, self._size)
        self._title_font.setBold(True)

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

        # 先合成到离屏：毛绒素材原样铺满，轮廓就是它自己的毛边
        buf = QPixmap(self.size())
        buf.fill(Qt.transparent)
        bp = QPainter(buf)
        bp.setRenderHint(QPainter.Antialiasing, True)
        bp.setRenderHint(QPainter.SmoothPixmapTransform, True)

        pm = _fuzz()
        if pm.isNull():
            bp.setPen(Qt.NoPen)
            bp.setBrush(QColor(250, 250, 252, 250))
            bp.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 16, 16)
        else:
            bp.drawPixmap(QRectF(0, 0, self.width(), self.height()), pm, QRectF(pm.rect()))

        # 中心柔光只落在毛上（SourceAtop 保留原有 alpha），不会在四角糊出一个白框
        grad = QRadialGradient(QPointF(self.width() / 2, self.height() / 2),
                               max(self.width(), self.height()) * 0.62)
        grad.setColorAt(0.0, QColor(255, 255, 255, 210))
        grad.setColorAt(0.55, QColor(255, 255, 255, 155))
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        bp.setCompositionMode(QPainter.CompositionMode_SourceAtop)
        bp.setPen(Qt.NoPen)
        bp.setBrush(grad)
        bp.drawRect(buf.rect())
        bp.end()

        p.drawPixmap(0, 0, buf)

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

