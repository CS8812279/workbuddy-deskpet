"""角色绘制：全部用 QPainter 矢量画，任意缩放不糊，状态动画由参数驱动。"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QLinearGradient, QPainter, QPainterPath,
                           QPen, QRadialGradient)

BASE = 200.0

PALETTE = {
    "idle":    ("#8FE7FF", "#3F6DFF"),
    "working": ("#9DF0FF", "#2F5BFF"),
    "done":    ("#B6F5D8", "#2ECB86"),
    "alert":   ("#FFC9C2", "#F04A3C"),
    "sleep":   ("#A8B6D8", "#5D6B92"),
}
INK = QColor("#101F45")
WHITE = QColor("#FFFFFF")


def _lerp(a: float, b: float, k: float) -> float:
    return a + (b - a) * k


def _mix(c1: QColor, c2: QColor, k: float) -> QColor:
    return QColor(
        int(_lerp(c1.red(), c2.red(), k)),
        int(_lerp(c1.green(), c2.green(), k)),
        int(_lerp(c1.blue(), c2.blue(), k)),
        int(_lerp(c1.alpha(), c2.alpha(), k)),
    )


@dataclass
class Confetti:
    x: float
    y: float
    vx: float
    vy: float
    rot: float
    vr: float
    color: QColor
    life: float = 0.0
    size: float = 4.0


CONFETTI_COLORS = ["#FFD166", "#6FE7B7", "#7FB2FF", "#FF8FA3", "#C69BFF", "#FFE9A8"]


def spawn_confetti(n: int = 16) -> list[Confetti]:
    out = []
    for _ in range(n):
        ang = random.uniform(-math.pi, 0)
        spd = random.uniform(90, 200)
        out.append(Confetti(
            x=100 + random.uniform(-18, 18),
            y=96 + random.uniform(-10, 10),
            vx=math.cos(ang) * spd * random.uniform(0.5, 1.0),
            vy=math.sin(ang) * spd,
            rot=random.uniform(0, 360),
            vr=random.uniform(-420, 420),
            color=QColor(random.choice(CONFETTI_COLORS)),
            size=random.uniform(3.0, 5.5),
        ))
    return out


def step_confetti(items: list[Confetti], dt: float) -> list[Confetti]:
    alive = []
    for c in items:
        c.life += dt
        if c.life > 1.5:
            continue
        c.vy += 260 * dt
        c.x += c.vx * dt
        c.y += c.vy * dt
        c.rot += c.vr * dt
        alive.append(c)
    return alive


def _body_path(cx: float, cy: float, rx: float, ry: float) -> QPainterPath:
    p = QPainterPath()
    p.moveTo(cx, cy - ry)
    p.cubicTo(cx - rx * 0.62, cy - ry * 0.98, cx - rx, cy - ry * 0.52, cx - rx * 0.98, cy + ry * 0.06)
    p.cubicTo(cx - rx * 0.96, cy + ry * 0.68, cx - rx * 0.56, cy + ry, cx, cy + ry)
    p.cubicTo(cx + rx * 0.56, cy + ry, cx + rx * 0.96, cy + ry * 0.68, cx + rx * 0.98, cy + ry * 0.06)
    p.cubicTo(cx + rx, cy - ry * 0.52, cx + rx * 0.62, cy - ry * 0.98, cx, cy - ry)
    p.closeSubpath()
    return p


def _star(p: QPainter, cx: float, cy: float, r: float, color: QColor) -> None:
    path = QPainterPath()
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.44
        pt = QPointF(cx + math.cos(ang) * rr, cy + math.sin(ang) * rr)
        if i == 0:
            path.moveTo(pt)
        else:
            path.lineTo(pt)
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(color))
    p.drawPath(path)


def draw_pet(
    p: QPainter,
    w: int,
    h: int,
    state: str,
    t: float,
    *,
    blink: float = 1.0,
    jump: float = 0.0,
    shake: float = 0.0,
    confetti: list[Confetti] | None = None,
    alert: float = 0.0,
) -> None:
    """在 (w,h) 画布内绘制角色。t 为秒，blink 0=闭眼 1=睁眼。"""
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    sx = w / BASE
    sy = h / BASE
    p.scale(sx, sy)

    breathe = math.sin(t * 2.1) * 0.5 + 0.5          # 0..1
    sway = math.sin(t * 1.15) * 1.8                   # 度
    bob = 0.0
    if state == "working":
        bob = -abs(math.sin(t * 6.2)) * 5.0
        sway = math.sin(t * 5.0) * 2.6
    elif state == "sleep":
        breathe = math.sin(t * 1.1) * 0.5 + 0.5
        bob = math.sin(t * 1.1) * 1.2

    cx, cy = 100.0, 112.0 + bob + jump
    rx, ry = 54.0, 51.0
    body_rx = rx * (1.0 - 0.012 * (breathe - 0.5))
    body_ry = ry * (1.0 + 0.030 * (breathe - 0.5))

    if state == "alert":
        cx += math.sin(t * 42) * 3.2 * alert
    cx += shake * 12

    top, bottom = PALETTE.get(state, PALETTE["idle"])
    c_top, c_bot = QColor(top), QColor(bottom)
    if alert > 0:
        c_top = _mix(c_top, QColor("#FFB3A7"), min(1.0, alert))
        c_bot = _mix(c_bot, QColor("#EF3B2D"), min(1.0, alert))

    # 地面阴影
    sh_w = body_rx * 1.55 * (1 + 0.03 * (breathe - 0.5))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(8, 14, 34, 46)))
    p.drawEllipse(QPointF(100, 176), sh_w, 8.5)

    # 待确认：背后红色脉冲环
    if alert > 0:
        for i in range(2):
            k = (t * 1.1 + i * 0.5) % 1.0
            p.setPen(QPen(QColor(255, 86, 70, int(90 * (1 - k) * alert)), 3.0))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(100, 118), 58 + k * 34, 52 + k * 30)

    p.translate(cx, cy)
    p.rotate(sway)
    p.translate(-cx, -cy)

    # 尾巴 / 小脚（跟随身体，跳跃时不脱节）
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(_mix(c_bot, QColor("#0B1230"), 0.12)))
    p.drawEllipse(QPointF(cx - 22, cy + body_ry * 0.94), 13, 9)
    p.drawEllipse(QPointF(cx + 22, cy + body_ry * 0.94), 13, 9)

    # 天线
    tip_y = cy - body_ry - 26
    p.setPen(QPen(QColor("#2E4FA8"), 2.4, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawLine(QPointF(100, cy - body_ry + 4), QPointF(100, tip_y + 5))
    glow = 0.5 + 0.5 * math.cos(t * 4.0 if state == "working" else t * 1.6)
    halo = QRadialGradient(QPointF(100, tip_y), 17)
    halo.setColorAt(0.0, QColor(255, 232, 140, int(130 * glow)))
    halo.setColorAt(0.65, QColor(255, 232, 140, int(46 * glow)))
    halo.setColorAt(1.0, QColor(255, 232, 140, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(halo))
    p.drawEllipse(QPointF(100, tip_y), 17, 17)
    p.setBrush(QBrush(QColor("#FFE27A" if state != "alert" else "#FF8A78")))
    p.drawEllipse(QPointF(100, tip_y), 5.4, 5.4)

    # 身体
    grad = QLinearGradient(QPointF(0, cy - body_ry), QPointF(0, cy + body_ry))
    grad.setColorAt(0.0, c_top)
    grad.setColorAt(1.0, c_bot)
    body = _body_path(cx, cy, body_rx, body_ry)
    p.setPen(QPen(QColor(16, 31, 69, 46), 1.6))
    p.setBrush(QBrush(grad))
    p.drawPath(body)

    # 顶部高光
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(255, 255, 255, 46)))
    p.drawEllipse(QPointF(84, cy - body_ry * 0.58), 20, 12)

    # 肚皮
    belly = QLinearGradient(QPointF(0, cy + 8), QPointF(0, cy + body_ry))
    belly.setColorAt(0.0, QColor(255, 255, 255, 120))
    belly.setColorAt(1.0, QColor(255, 255, 255, 40))
    p.setBrush(QBrush(belly))
    p.drawEllipse(QPointF(100, cy + body_ry * 0.42), body_rx * 0.66, body_ry * 0.46)

    # 腮红
    blush = 150 if state != "sleep" else 60
    p.setBrush(QBrush(QColor(255, 122, 160, blush)))
    p.drawEllipse(QPointF(cx - body_rx * 0.62, cy + body_ry * 0.20), 8.5, 5.2)
    p.drawEllipse(QPointF(cx + body_rx * 0.62, cy + body_ry * 0.20), 8.5, 5.2)

    # 眼睛
    eye_y = cy + body_ry * 0.02
    eye_dx = body_rx * 0.34
    eye_open = max(0.06, min(1.0, blink))
    if state == "done":
        _star(p, cx - eye_dx, eye_y, 10.0, QColor("#FFFFFF"))
        _star(p, cx + eye_dx, eye_y, 10.0, QColor("#FFFFFF"))
    elif state == "sleep":
        p.setPen(QPen(INK, 2.6, Qt.SolidLine, Qt.RoundCap))
        for dx in (-eye_dx, eye_dx):
            p.drawArc(QRectF(cx + dx - 9, eye_y - 6, 18, 12), 200 * 16, 140 * 16)
    else:
        for dx in (-eye_dx, eye_dx):
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(INK))
            p.drawEllipse(QPointF(cx + dx, eye_y), 8.6, 11.4 * eye_open)
            if eye_open > 0.45:
                p.setBrush(QBrush(WHITE))
                p.drawEllipse(QPointF(cx + dx - 2.6, eye_y - 4.0 * eye_open), 3.1, 3.7)
                p.setBrush(QBrush(QColor(255, 255, 255, 150)))
                p.drawEllipse(QPointF(cx + dx + 2.8, eye_y + 3.4), 1.7, 2.0)

    # 嘴
    mouth_y = cy + body_ry * 0.40
    if state == "alert":
        p.setPen(QPen(INK, 2.2))
        p.setBrush(QBrush(QColor(120, 24, 24)))
        p.drawEllipse(QPointF(cx, mouth_y), 4.6, 5.6)
    elif state == "done":
        p.setPen(QPen(INK, 2.4, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(QBrush(QColor(255, 255, 255, 90)))
        path = QPainterPath()
        path.moveTo(cx - 8, mouth_y - 1)
        path.quadTo(cx, mouth_y + 8, cx + 8, mouth_y - 1)
        path.closeSubpath()
        p.drawPath(path)
    elif state == "sleep":
        p.setPen(QPen(INK, 2.0, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx - 4, mouth_y), QPointF(cx + 4, mouth_y))
    elif state == "working":
        p.setPen(QPen(INK, 2.0))
        p.setBrush(QBrush(QColor(60, 24, 60, 90)))
        p.drawEllipse(QPointF(cx, mouth_y + 1), 3.4, 4.2)
    else:
        p.setPen(QPen(INK, 2.2, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(cx - 7, mouth_y - 5, 14, 11), 200 * 16, 140 * 16)

    # 待确认徽标
    if state == "alert":
        bx, by = cx + body_rx * 0.92, cy - body_ry * 0.78
        p.setPen(QPen(QColor(255, 255, 255, 200), 2.0))
        p.setBrush(QBrush(QColor("#F04438")))
        p.drawEllipse(QPointF(bx, by), 13.5, 13.5)
        p.setPen(QPen(WHITE, 3.0, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(bx, by - 6.5), QPointF(bx, by + 1.5))
        p.drawPoint(QPointF(bx, by + 6.5))

    p.restore()

    # 工作小火花
    if state == "working":
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.scale(w / BASE, h / BASE)
        for i in range(3):
            k = (t * 1.5 + i / 3.0) % 1.0
            ang = -math.pi / 2 + k * math.pi * 2 * 0.55 - 0.6
            px = 100 + math.cos(ang) * 68
            py = 128 + math.sin(ang) * 62
            alpha = int(200 * (1 - k))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(255, 236, 150, alpha)))
            p.drawEllipse(QPointF(px, py), 2.6, 2.6)
        p.restore()

    # 睡觉 zzz
    if state == "sleep":
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.scale(w / BASE, h / BASE)
        for i in range(3):
            k = (t * 0.5 + i / 3.0) % 1.0
            alpha = int(200 * (1 - k))
            size = 8 + k * 8
            p.setPen(QPen(QColor(180, 205, 255, alpha), 2.0))
            f = p.font()
            f.setPointSizeF(size)
            f.setBold(True)
            p.setFont(f)
            p.drawText(QPointF(134 + k * 16, 78 - k * 30), "z")
        p.restore()

    # 彩带
    if confetti:
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.scale(w / BASE, h / BASE)
        for c in confetti:
            alpha = max(0, int(255 * (1 - c.life / 1.5)))
            p.save()
            p.translate(c.x, c.y)
            p.rotate(c.rot)
            col = QColor(c.color)
            col.setAlpha(alpha)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(col))
            p.drawRoundedRect(QRectF(-c.size / 2, -c.size / 4, c.size, c.size / 2), 1, 1)
            p.restore()
        p.restore()
