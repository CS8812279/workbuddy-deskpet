"""图片皮肤：用生成的立绘帧替代程序绘制的团子。

帧目录约定：assets/<skin>/frames/{idle,blink,alert,done,sleep}.png
所有帧同尺寸、底边对齐，切换时不会跳动。
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

FRAMES = ("idle", "blink", "alert", "done", "sleep",
          "happy", "shy", "angry", "sad")
# 情绪名 -> 立绘帧名（没有专属帧的情绪复用别的帧）
MOOD_FRAME = {"surprise": "alert"}
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
        self.wings = False
        meta = root.parent / "skin.json"
        if meta.exists():
            try:
                import json

                self.wings = bool(json.loads(meta.read_text(encoding="utf-8")).get("wings"))
            except Exception:
                self.wings = False

    def __bool__(self) -> bool:
        return bool(self.frames)

    def size_for(self, scale: float) -> tuple[int, int]:
        body_h = max(120, int(MAX_H * scale))
        h = int(body_h * (1.0 + HEADROOM))
        return max(60, int(body_h * self.aspect)), h

    # ---------------- 绘制 ----------------
    def draw(self, p: QPainter, w: int, h: int, state: str, t: float, *,
             blink: float = 1.0, jump: float = 0.0, alert: float = 0.0,
             confetti: list | None = None,
             mood: str | None = None, mood_alpha: float = 0.0) -> None:
        frame = "idle"
        mood_frame = MOOD_FRAME.get(mood or "", mood or "")
        if state == "alert":
            frame = "alert"
        elif mood_frame and mood_frame in self.frames:
            frame = mood_frame
        elif state == "done":
            frame = "done"
        elif state == "sleep":
            frame = "sleep"
        elif blink < 0.5:
            frame = "blink"
        pm = self.frames.get(frame) or self.frames["idle"]

        breathe = 1.0 + 0.014 * math.sin(t * 2.1)
        bob = 0.0
        sway = 0.0
        wing_amp, wing_speed = 0.0, 1.0
        if self.wings:
            if state == "working":
                wing_amp, wing_speed = 4.2, 3.6     # 干活时翅膀轻轻扇
            elif state == "sleep":
                wing_amp, wing_speed = 1.0, 0.7
            else:
                wing_amp, wing_speed = 1.6, 1.3
        if state == "working":
            bob = -abs(math.sin(t * 6.2)) * 5.5
            sway = math.sin(t * 4.6) * 0.9
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
        if self.wings and wing_amp > 0:
            self._draw_winged(p, pm, w, body_h, body_top, t, wing_amp, wing_speed)
        else:
            p.drawPixmap(QRectF(0, body_top, w, body_h), pm, QRectF(pm.rect()))
        p.restore()

        if alert > 0:
            self._draw_alert_badge(p, w, h, alert)
        if confetti:
            self._draw_confetti(p, w, h, confetti)
        if state == "sleep":
            self._draw_zzz(p, w, h, t)

    def _draw_winged(self, p: QPainter, pm: QPixmap, w: int, body_h: float,
                     body_top: float, t: float, amp: float, speed: float) -> None:
        """把立绘切成竖条，两侧按正弦上下错位——翅膀就活了，身体中线不动。

        每条目标高度多给 2*|dy|，源矩形多给半像素，保证没有缝。
        """
        strips = 28
        src_w = pm.width() / strips
        for i in range(strips):
            x0 = w * i / strips
            x1 = w * (i + 1) / strips
            k = abs((i + 0.5) / strips - 0.5) * 2.0     # 0=中线，1=最外侧
            dy = math.sin(t * speed - k * 2.4) * amp * (k ** 1.7)
            pad = abs(dy)
            p.drawPixmap(
                QRectF(x0, body_top + dy - pad, x1 - x0, body_h + pad * 2),
                pm, QRectF(i * src_w, 0, src_w + 0.6, pm.height()),
            )

    # ---------------- 情绪 ----------------
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

    def _clamp(px: float, py: float, w: int, h: int, margin: float) -> tuple[float, float]:
        return (min(max(px, margin), w - margin), min(max(py, margin), h - margin))

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
