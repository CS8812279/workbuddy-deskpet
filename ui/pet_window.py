"""桌宠窗口：透明无边框、置顶、可拖拽、状态动画。"""
from __future__ import annotations

import math
import random

from PySide6.QtCore import (QEasingCurve, QPoint, QPropertyAnimation, QRectF,
                            QTimer, Qt, Signal)
from PySide6.QtGui import QAction, QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from .character import (BASE, Confetti, draw_pet, spawn_confetti, step_confetti)
from .sprite import SpriteSkin

IDLE, WORKING, DONE, ALERT, SLEEP = "idle", "working", "done", "alert", "sleep"


class PetWindow(QWidget):
    clicked = Signal()
    double_clicked = Signal()
    drag_started = Signal()
    drag_finished = Signal()
    context_requested = Signal(QPoint)

    def __init__(self, scale: float = 1.0, skin: SpriteSkin | None = None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)
        self.setToolTip("左键查看面板 · 拖拽移动 · 右键菜单")

        self._scale = scale
        self.skin = skin
        self._apply_size()

        self.state = IDLE
        self._t = 0.0
        self.mood: str | None = None
        self._mood_t0 = 0.0
        self._mood_until = 0.0
        self._dt = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self._blink_at = 2.0
        self._blink_end = 0.0
        self._jump_t0 = -10.0
        self._alert_at = 0.0
        self._confetti: list[Confetti] = []
        self._press_global = None
        self._press_win = None
        self._dragging = False
        self._was_dragging = False
        self._mover = None

    # ---------------- 生命周期 ----------------
    def _tick(self) -> None:
        self._dt = self._timer.interval() / 1000.0
        self._t += self._dt

        if self._t >= self._blink_at:
            self._blink_end = self._t + 0.14
            self._blink_at = self._t + random.uniform(2.4, 6.0)

        if self._confetti:
            self._confetti = step_confetti(self._confetti, self._dt)

        # 情绪到期必须自己收回，否则立绘会永远停在那一帧、连眨眼都没了
        if self.mood and self._t >= self._mood_until:
            self.mood = None

        if self.state == DONE and self._t - self._jump_t0 > 2.4:
            self.set_state(IDLE if not self._confetti else DONE)

        self.update()

    def set_state(self, state: str) -> None:
        if state == self.state:
            return
        self.state = state
        if state == DONE:
            self._jump_t0 = self._t
            self._confetti = spawn_confetti(18)
        elif state == ALERT:
            self._alert_at = self._t
            self._confetti = []

    def set_scale(self, scale: float) -> None:
        self._scale = scale
        self._apply_size()
        self.update()

    def _apply_size(self) -> None:
        if self.skin:
            w, h = self.skin.size_for(self._scale)
        else:
            w = h = max(120, int(BASE * self._scale))
        self.setFixedSize(w, h)

    def set_always_on_top(self, on: bool) -> None:
        pos = self.pos()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        self.show()
        self.move(pos)

    @property
    def center_point(self) -> QPoint:
        return self.geometry().center()

    # ---------------- 绘制 ----------------
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), Qt.transparent)

        blink = 1.0
        if self._t < self._blink_end:
            k = 1.0 - (self._blink_end - self._t) / 0.14
            blink = 1.0 - 0.94 * math.sin(max(0.0, min(1.0, k)) * math.pi)
        if self.state == SLEEP:
            blink = 1.0

        jump = 0.0
        if self.state == DONE:
            p_ = self._t - self._jump_t0
            if 0 <= p_ < 1.0:
                jump = -abs(math.sin(p_ * math.pi * 2.0)) * 26.0 * (1.0 - p_ * 0.55)

        alert = 1.0 if self.state == ALERT else max(
            0.0, 1.0 - (self._t - self._alert_at) * 2.0
        )

        if self.skin:
            self._paint_skin(p, blink, jump, alert)
            return

        draw_pet(
            p, self.width(), self.height(), self.state, self._t,
            blink=blink, jump=jump, confetti=self._confetti, alert=alert,
        )

    def _paint_skin(self, p, blink: float, jump: float, alert: float) -> None:
        self.skin.draw(
            p, self.width(), self.height(), self.state, self._t,
            blink=blink, jump=jump * (self.height() / BASE),
            alert=alert, confetti=self._confetti,
            mood=self.mood, mood_alpha=self.mood_alpha(),
        )

    # ---------------- 情绪 ----------------
    def set_mood(self, mood: str | None, seconds: float = 2.4) -> None:
        self.mood = mood
        self._mood_t0 = self._t
        self._mood_until = self._t + seconds if mood else 0.0
        self.update()

    def mood_alpha(self) -> float:
        if not self.mood:
            return 0.0
        if self._t >= self._mood_until:
            return 0.0
        fade_in = min(1.0, (self._t - self._mood_t0) / 0.18)
        fade_out = min(1.0, (self._mood_until - self._t) / 0.35)
        return max(0.0, min(fade_in, fade_out))

    # ---------------- 交互 ----------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.RightButton:
            self.context_requested.emit(event.globalPosition().toPoint())
            return
        if event.button() == Qt.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._press_win = self.pos()
            self._dragging = False

    def mouseMoveEvent(self, event) -> None:
        if self._press_global is None or not (event.buttons() & Qt.LeftButton):
            return
        cur = event.globalPosition().toPoint()
        delta = cur - self._press_global
        if not self._dragging and (abs(delta.x()) > 3 or abs(delta.y()) > 3):
            self._dragging = True
        if self._dragging:
            if not self._was_dragging:
                self._was_dragging = True
                self.drag_started.emit()
            self.move(self._press_win + delta)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        if not self._dragging:
            self.clicked.emit()
        else:
            self.snap_to_edge()
            if self._was_dragging:
                self.drag_finished.emit()
        self._press_global = None
        self._dragging = False
        self._was_dragging = False

    # ---------------- 运动 ----------------
    def animate_to(self, target: QPoint, ms: int = 420) -> None:
        start = self.pos()
        if start == target:
            return
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(ms)
        anim.setStartValue(start)
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._mover = anim

    def snap_to_edge(self, margin: int = 0) -> None:
        screen = QApplication.screenAt(self.center_point) or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        pos = self.pos()
        x, y = pos.x(), pos.y()
        if x - area.left() < 24:
            x = area.left() + margin
        elif area.right() - (x + self.width()) < 24:
            x = area.right() - self.width() - margin
        if y - area.top() < 24:
            y = area.top() + margin
        elif area.bottom() - (y + self.height()) < 24:
            y = area.bottom() - self.height() - margin
        if (x, y) != (pos.x(), pos.y()):
            self.animate_to(QPoint(x, y), 220)

    def center_target(self) -> QPoint:
        screen = QApplication.screenAt(self.center_point) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        return QPoint(
            area.center().x() - self.width() // 2,
            int(area.center().y() - self.height() / 2 + area.height() * 0.08),
        )

    def clamp_to_screen(self, margin: int = 8) -> None:
        screen = QApplication.screenAt(self.center_point) or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = min(max(self.x(), area.left() + margin), area.right() - self.width() - margin)
        y = min(max(self.y(), area.top() + margin), area.bottom() - self.height() - margin)
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)
