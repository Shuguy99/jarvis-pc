"""HUD-оверлей в стиле Старка: полупрозрачное окно с реактором и логом."""

from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..assistant import Event, State
from ..config import UiConfig

STATE_LABELS = {
    State.IDLE: "ОЖИДАНИЕ",
    State.LISTENING: "СЛУШАЮ",
    State.THINKING: "АНАЛИЗ",
    State.SPEAKING: "ОТВЕТ",
}
STATE_SPEED = {
    State.IDLE: 0.6,
    State.LISTENING: 2.4,
    State.THINKING: 3.6,
    State.SPEAKING: 1.8,
}
CORNER_MARGIN = 24


class ReactorWidget(QWidget):
    """Анимированное «ядро реактора», реагирующее на состояние ассистента."""

    def __init__(self, accent: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accent = QColor(accent)
        self._phase = 0.0
        self._state = State.IDLE
        self.setFixedSize(120, 120)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def _tinted(self, alpha: int) -> QColor:
        """Акцентный цвет с заданной прозрачностью."""
        return QColor(self._accent.red(), self._accent.green(), self._accent.blue(), alpha)

    def set_state(self, state: State) -> None:
        """Меняет режим анимации."""
        self._state = state
        self.update()

    def _tick(self) -> None:
        """Продвигает фазу анимации."""
        self._phase += 0.05 * STATE_SPEED.get(self._state, 1.0)
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        """Рисует пульсирующее ядро и вращающиеся дуги."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        center = self.rect().center()
        pulse = 0.5 + 0.5 * math.sin(self._phase * 2)
        core_radius = side * (0.20 + 0.05 * pulse)

        gradient = QRadialGradient(center, core_radius * 2.6)
        glow = QColor(self._accent)
        glow.setAlpha(int(150 + 80 * pulse))
        gradient.setColorAt(0.0, glow)
        gradient.setColorAt(0.45, self._tinted(60))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(center, int(core_radius * 2.6), int(core_radius * 2.6))

        painter.setBrush(QColor(230, 250, 255, 230))
        painter.drawEllipse(center, int(core_radius), int(core_radius))

        for index in range(3):
            radius = side * (0.30 + 0.07 * index)
            pen = QPen(self._tinted(200 - 50 * index))
            pen.setWidthF(2.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            span = 90 + 40 * index
            start = int((self._phase * (60 + 25 * index) + index * 120) % 360)
            direction = -1 if index % 2 else 1
            painter.drawArc(
                int(center.x() - radius),
                int(center.y() - radius),
                int(radius * 2),
                int(radius * 2),
                start * 16,
                direction * span * 16,
            )
        painter.end()


class HudWindow(QWidget):
    """Окно-оверлей: состояние, последняя команда и ответ."""

    event_received = Signal(object)

    def __init__(self, config: UiConfig, on_close: Callable[[], None]) -> None:
        super().__init__()
        self._config = config
        self._on_close = on_close
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setWindowOpacity(config.opacity)
        self.resize(config.width, config.height)

        self._reactor = ReactorWidget(config.accent)
        self._state_label = QLabel(STATE_LABELS[State.IDLE])
        self._state_label.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        self._state_label.setStyleSheet(f"color: {config.accent};")
        self._user_label = QLabel("")
        self._reply_label = QLabel("J.A.R.V.I.S. онлайн")
        for label in (self._user_label, self._reply_label):
            label.setWordWrap(True)
            label.setFont(QFont("Consolas", 10))
        self._user_label.setStyleSheet("color: #9fe8ff;")
        self._reply_label.setStyleSheet("color: #eaffff;")

        text_column = QVBoxLayout()
        text_column.addWidget(self._state_label)
        text_column.addWidget(self._user_label)
        text_column.addWidget(self._reply_label)
        text_column.addStretch(1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.addWidget(self._reactor)
        layout.addLayout(text_column, 1)

        self.event_received.connect(self._apply_event)
        self._place()

    def _place(self) -> None:
        """Ставит окно в выбранный угол экрана."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        corner = self._config.corner
        x = area.left() + CORNER_MARGIN
        y = area.top() + CORNER_MARGIN
        if corner.endswith("right"):
            x = area.right() - self.width() - CORNER_MARGIN
        if corner.startswith("bottom"):
            y = area.bottom() - self.height() - CORNER_MARGIN
        self.move(x, y)

    def paintEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        """Рисует затемнённую панель с неоновой рамкой."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        accent = QColor(self._config.accent)
        painter.setBrush(QColor(6, 14, 22, 210))
        pen = QPen(QColor(accent.red(), accent.green(), accent.blue(), 170))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 14, 14)
        painter.end()

    def submit(self, event: Event) -> None:
        """Потокобезопасно передаёт событие в интерфейс."""
        self.event_received.emit(event)

    def _apply_event(self, event: Event) -> None:
        """Обновляет тексты и анимацию по событию ассистента."""
        self._state_label.setText(STATE_LABELS.get(event.state, event.state.value))
        self._reactor.set_state(event.state)
        if not event.text:
            return
        if event.speaker == "user":
            self._user_label.setText(f"> {event.text}")
        else:
            self._reply_label.setText(event.text)

    def mousePressEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        """Запоминает точку захвата для перетаскивания окна."""
        self._drag_origin = event.globalPosition().toPoint() - self.pos()  # type: ignore[attr-defined]

    def mouseMoveEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        """Перетаскивает окно за любую точку панели."""
        origin = getattr(self, "_drag_origin", None)
        if origin is not None:
            self.move(event.globalPosition().toPoint() - origin)  # type: ignore[attr-defined]

    def showEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        """Поднимает окно и берёт фокус, чтобы Escape срабатывал сразу."""
        super().showEvent(event)  # type: ignore[arg-type]
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def keyPressEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        """Escape закрывает оверлей."""
        if event.key() == Qt.Key.Key_Escape:  # type: ignore[attr-defined]
            self.close()

    def closeEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        """Сообщает ядру о закрытии интерфейса."""
        self._on_close()
        event.accept()  # type: ignore[attr-defined]
