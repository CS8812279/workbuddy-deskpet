"""图片皮肤：用生成的立绘帧替代程序绘制的团子。

帧目录约定：assets/<skin>/frames/{idle,blink,alert,done,sleep}.png
所有帧同尺寸、底边对齐，切换时不会跳动。
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap

FRAMES = ("idle", "blink", "alert", "done", "sleep")
MAX_H = 300          # scale=1.0 时角色本身的高度
HEADROOM = 0.14      # 窗口顶部预留，供弹跳/上浮使用，避免头被裁


class SpriteSkin:
    def __init__(self, root: Path):
        self.root = root
        self.frames: dict[str, QPixmap] = {}
        for name in FRAMES:
            p = root / f"{name}.png"
            if p.exists():
                pm = QPixmap(str(p))
                if not pm.isNull():
                    self.frames[name] = pm
        if "idle" not in self.frames:
            self.frames.clear()
            return
        base = self.frames["idle"]
        self.aspect = base.width() / max(1, base.height())

    def __bool__(self) -> bool:
        return bool(self.frames)

    def size_for(self, scale: float) -> tuple[int, int]:
        body_h = max(120, int(MAX_H * scale))
        h = int(body_h * (1.0 + HEADROOM))
        return max(60, int(body_h * self.aspect)), h

    # ---------------- 绘制 ----------------
    def draw(self, p: QPainter, w: int, h: int, state: str, t: float, *,
             blink: float = 1.0, jump: float = 0.0, alert: float = 0.0,
             confetti: list | None = None) -> None:
        frame = "idle"
        if state == "done":
            frame = "done"
        elif state == "alert":
            frame = "alert"
        elif state == "sleep":
            frame = "sleep"
        elif blink < 0.5:
            frame = "blink"
        pm = self.frames.get(frame) or self.frames["idle"]

        breathe = 1.0 + 0.014 * math.sin(t * 2.1)
        bob = 0.0
        sway = 0.0
        if state == "working":
            bob = -abs(math.sin(t * 6.2)) * 4.0
            sway = math.sin(t * 4.6) * 0.5
        elif state == "sleep":
            breathe = 1.0 + 0.02 * math.sin(t * 1.1)
        elif state == "done":
            breathe = 1.0 + 0.02 * math.sin(t * 9.0)

        dx = math.sin(t * 42) * 3.0 * alert

        p.save()
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)

        if alert > 0:
            self._draw_alert_rings(p, w, h, t, alert)

        # 脚下接触阴影，图片本身没有阴影，补一层接地感
        shadow_w = w * (0.42 if state != "done" else 0.34)
        shadow_a = 62 if state != "alert" else 34
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(6, 12, 28, shadow_a))
        p.drawEllipse(QPointF(w / 2, h - 4), shadow_w, max(4.0, h * 0.018))

        body_h = h / (1.0 + HEADROOM)
        body_top = h - body_h

        p.translate(w / 2 + dx, h + jump + bob)
        p.rotate(sway)
        p.scale(1.0, breathe)
        p.translate(-w / 2, -h)
        p.drawPixmap(QRectF(0, body_top, w, body_h), pm, QRectF(pm.rect()))
        p.restore()

        if alert > 0:
            self._draw_alert_badge(p, w, h, alert)
        if confetti:
            self._draw_confetti(p, w, h, confetti)
        if state == "working":
            self._draw_sparks(p, w, h, t)
            self._draw_thinking(p, w, h, t)
        if state == "sleep":
            self._draw_zzz(p, w, h, t)

    # ---------------- 特效 ----------------
    def _draw_alert_rings(self, p: QPainter, w: int, h: int, t: float, k: float) -> None:
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        for i in range(2):
            prog = (t * 1.1 + i * 0.5) % 1.0
            alpha = int(58 * (1 - prog) * k)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 96, 78, alpha))
            rr = w * (0.30 + prog * 0.22)
            p.drawEllipse(QPointF(w / 2, h * 0.58), rr, rr * 0.72)
        p.restore()

    def _draw_alert_badge(self, p: QPainter, w: int, h: int, k: float) -> None:
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        bx, by, r = w * 0.84, h * 0.075, max(9.0, w * 0.09)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(240, 68, 56, int(255 * k)))
        p.drawEllipse(QPointF(bx, by), r, r)
        p.setPen(Qt.white)
        f = p.font()
        f.setPointSizeF(max(8.0, r * 0.9))
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(bx - r, by - r, r * 2, r * 2), Qt.AlignCenter, "!")
        p.restore()

    def _draw_confetti(self, p: QPainter, w: int, h: int, items: list) -> None:
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        for c in items:
            alpha = max(0, int(255 * (1 - c.life / 1.5)))
            p.save()
            p.translate(c.x / 200.0 * w, c.y / 200.0 * h)
            p.rotate(c.rot)
            col = QColor(c.color)
            col.setAlpha(alpha)
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            size = c.size * (h / 200.0)
            p.drawRoundedRect(QRectF(-size / 2, -size / 4, size, size / 2), 1, 1)
            p.restore()
        p.restore()

    def _draw_thinking(self, p: QPainter, w: int, h: int, t: float) -> None:
        """头顶三个跳动的点：贴着角色，永远不越出窗口（否则贴屏幕边会被切掉）。"""
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        body_h = h / (1.0 + HEADROOM)
        r = max(1.8, min(4.6, w * 0.020))
        gap = r * 2.6
        base_y = h - body_h + r * 1.6          # 刚好压在发顶
        for i in range(3):
            phase = (t * 2.2 - i * 0.28) % 1.0
            lift = -math.sin(phase * math.pi * 2) * r * 1.1
            alpha = 120 + int(90 * (0.5 + 0.5 * math.sin(phase * math.pi * 2)))
            px = w / 2 + (i - 1) * gap
            py = base_y + lift
            px, py = self._clamp(px, py, w, h, r + 1)
            p.setBrush(QColor(150, 200, 255, min(240, alpha)))
            p.drawEllipse(QPointF(px, py), r, r)
        p.restore()

    @staticmethod
    def _clamp(px: float, py: float, w: int, h: int, margin: float) -> tuple[float, float]:
        return (min(max(px, margin), w - margin), min(max(py, margin), h - margin))

    def _draw_sparks(self, p: QPainter, w: int, h: int, t: float) -> None:
        """绕身体转的小光点，半径按窗口短边算，避免飞出画面。"""
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        radius = min(w, h) * 0.30
        for i in range(3):
            k = (t * 1.5 + i / 3.0) % 1.0
            ang = -math.pi * 0.9 + k * math.pi * 1.6
            px = w / 2 + math.cos(ang) * radius
            py = h * 0.46 + math.sin(ang) * radius * 0.85
            r = max(1.4, min(3.0, w * 0.012))
            px, py = self._clamp(px, py, w, h, r + 1)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 236, 150, int(200 * (1 - k))))
            p.drawEllipse(QPointF(px, py), r, r)
        p.restore()

    def _draw_zzz(self, p: QPainter, w: int, h: int, t: float) -> None:
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        for i in range(3):
            k = (t * 0.5 + i / 3.0) % 1.0
            alpha = int(200 * (1 - k))
            p.setPen(QColor(180, 210, 255, alpha))
            f = p.font()
            f.setPointSizeF(7 + k * 8)
            f.setBold(True)
            p.setFont(f)
            p.drawText(QPointF(w * 0.66 + k * w * 0.16, h * 0.42 - k * h * 0.18), "z")
        p.restore()


def load_skin(path: Path) -> SpriteSkin | None:
    skin = SpriteSkin(path)
    return skin if skin else None


def load_custom_skin(file: Path) -> SpriteSkin | None:
    """用户导入的单张 PNG：一张图充当所有状态，至少保证不崩。"""
    pm = QPixmap(str(file))
    if pm.isNull():
        return None
    skin = SpriteSkin.__new__(SpriteSkin)
    skin.root = file.parent
    skin.frames = {name: pm for name in FRAMES}
    skin.aspect = pm.width() / max(1, pm.height())
    return skin
