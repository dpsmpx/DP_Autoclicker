"""Небольшие переиспользуемые элементы интерфейса."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..icons import icon
from ..theme import PALETTE


class Card(QFrame):
    """Скруглённый контейнер-«карточка» с необязательным заголовком."""

    def __init__(self, title: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 12, 14, 12)
        self._layout.setSpacing(9)
        if title:
            label = QLabel(title)
            label.setProperty("role", "section")
            self._layout.addWidget(label)

    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget: QWidget) -> QWidget:
        self._layout.addWidget(widget)
        return widget

    def add_row(self, *widgets: QWidget, spacing: int = 8) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(spacing)
        for widget in widgets:
            row.addWidget(widget)
        self._layout.addLayout(row)
        return row


class Divider(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Divider")
        self.setFixedHeight(1)


class ToggleSwitch(QAbstractButton):
    """Переключатель-«тумблер» вместо галочки."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(42, 24)
        self._offset = 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.toggled.connect(self._animate)

    def get_offset(self) -> float:
        return self._offset

    def set_offset(self, value: float) -> None:
        self._offset = value
        self.update()

    offset = Property(float, get_offset, set_offset)

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - Qt API
        super().setChecked(checked)
        self._offset = 1.0 if checked else 0.0
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(42, 24)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        track = QRectF(1, 3, self.width() - 2, self.height() - 6)
        off = QColor(PALETTE.border)
        on = QColor(PALETTE.accent)
        color = QColor(
            int(off.red() + (on.red() - off.red()) * self._offset),
            int(off.green() + (on.green() - off.green()) * self._offset),
            int(off.blue() + (on.blue() - off.blue()) * self._offset),
        )
        if not self.isEnabled():
            color.setAlpha(90)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(track, track.height() / 2, track.height() / 2)

        radius = (self.height() - 8) / 2
        cx = 5 + radius + self._offset * (self.width() - 10 - radius * 2)
        painter.setBrush(QColor("#F2F5FF" if self.isEnabled() else PALETTE.faint))
        painter.drawEllipse(QRectF(cx - radius, 4, radius * 2, radius * 2))
        painter.end()


class SwitchRow(QWidget):
    """Строка «подпись + описание + тумблер»."""

    toggled = Signal(bool)

    def __init__(
        self, title: str, hint: str = "", checked: bool = False, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        texts = QVBoxLayout()
        texts.setSpacing(1)
        self.title_label = QLabel(title)
        texts.addWidget(self.title_label)
        if hint:
            hint_label = QLabel(hint)
            hint_label.setProperty("role", "hint")
            hint_label.setWordWrap(True)
            texts.addWidget(hint_label)
        layout.addLayout(texts, 1)

        self.switch = ToggleSwitch()
        self.switch.setChecked(checked)
        self.switch.toggled.connect(self.toggled)
        layout.addWidget(self.switch, 0, Qt.AlignmentFlag.AlignTop)

    def isChecked(self) -> bool:  # noqa: N802 - Qt-подобное имя
        return self.switch.isChecked()

    def setChecked(self, value: bool) -> None:  # noqa: N802
        self.switch.setChecked(value)


class SliderRow(QWidget):
    """Подпись, ползунок и текущее значение в одну строку."""

    valueChanged = Signal(float)

    def __init__(
        self,
        title: str,
        minimum: float,
        maximum: float,
        value: float,
        step: float = 1.0,
        suffix: str = "",
        decimals: int = 0,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._step = step
        self._suffix = suffix
        self._decimals = decimals

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        head = QHBoxLayout()
        head.setSpacing(6)
        self.title_label = QLabel(title)
        self.title_label.setProperty("role", "muted")
        self.value_label = QLabel()
        self.value_label.setProperty("role", "value")
        head.addWidget(self.title_label, 1)
        head.addWidget(self.value_label, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(head)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(int(round(minimum / step)))
        self.slider.setMaximum(int(round(maximum / step)))
        self.slider.setValue(int(round(value / step)))
        self.slider.valueChanged.connect(self._on_change)
        layout.addWidget(self.slider)
        self._update_label()

    def _on_change(self, _raw: int) -> None:
        self._update_label()
        self.valueChanged.emit(self.value())

    def _update_label(self) -> None:
        text = f"{self.value():.{self._decimals}f}"
        self.value_label.setText(f"{text}{self._suffix}")

    def value(self) -> float:
        return self.slider.value() * self._step

    def setValue(self, value: float) -> None:  # noqa: N802
        self.slider.setValue(int(round(value / self._step)))
        self._update_label()

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        super().setEnabled(enabled)
        self.slider.setEnabled(enabled)


class StatusPill(QWidget):
    """Индикатор состояния: цветная точка и текст."""

    def __init__(self, text: str = "Готов", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._color = QColor(PALETTE.faint)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        self._dot = _Dot(self)
        layout.addWidget(self._dot)
        self.label = QLabel(text)
        self.label.setProperty("role", "muted")
        layout.addWidget(self.label)
        layout.addStretch(1)

    def set_state(self, text: str, color: str) -> None:
        self.label.setText(text)
        self._dot.set_color(color)


class _Dot(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(9, 9)
        self._color = QColor(PALETTE.faint)

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        glow = QColor(self._color)
        glow.setAlpha(70)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(self.rect())
        painter.setBrush(self._color)
        painter.drawEllipse(self.rect().adjusted(2, 2, -2, -2))
        painter.end()


def tool_button(
    name: str,
    tooltip: str,
    on_click: Optional[Callable[[], None]] = None,
    color: str = PALETTE.muted,
    checkable: bool = False,
    size: int = 18,
) -> QToolButton:
    """Кнопка-иконка для панелей инструментов."""
    button = QToolButton()
    button.setIcon(icon(name, color, size))
    button.setIconSize(QSize(size, size))
    button.setToolTip(tooltip)
    button.setCheckable(checkable)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFixedSize(30, 28)
    if on_click:
        button.clicked.connect(on_click)
    return button


def text_button(
    text: str,
    variant: str = "",
    icon_name: str = "",
    on_click: Optional[Callable[[], None]] = None,
    icon_color: str = "",
) -> QPushButton:
    """Обычная кнопка с текстом и (необязательно) иконкой."""
    button = QPushButton(text)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if variant:
        button.setProperty("variant", variant)
    if icon_name:
        default = "#0B1020" if variant in ("primary", "success") else PALETTE.muted
        button.setIcon(icon(icon_name, icon_color or default, 18))
        button.setIconSize(QSize(18, 18))
    if on_click:
        button.clicked.connect(on_click)
    return button


def section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "section")
    return label


def hint_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "hint")
    label.setWordWrap(True)
    return label


def expanding() -> QWidget:
    spacer = QWidget()
    spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    return spacer
