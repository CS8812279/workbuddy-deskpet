"""图标：直接用角色绘制生成托盘图标，保证与桌宠同一张脸。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap

from .character import draw_pet


def make_pixmap(size: int = 64, state: str = "idle") -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    # 角色画布 200x200，裁掉底部阴影区域后铺满图标
    p.scale(size / 200.0, size / 200.0)
    draw_pet(p, 200, 200, state, 0.0)
    p.end()
    return pm


def make_icon(state: str = "idle") -> QIcon:
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128):
        icon.addPixmap(make_pixmap(s, state))
    return icon


def make_icon_from_skin(skin, state: str = "idle") -> QIcon | None:
    """用立绘的头部区域做托盘图标，和桌宠同一张脸。"""
    if not skin or not skin.frames:
        return None
    pm = skin.frames.get(state) or skin.frames.get("idle")
    if pm is None or pm.isNull():
        return None
    side = min(pm.width(), int(pm.height() * 0.42))
    src = pm.copy((pm.width() - side) // 2, 0, side, side)
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128):
        icon.addPixmap(src.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    return icon
