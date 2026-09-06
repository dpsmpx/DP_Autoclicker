"""Прицел выбора координат: полноэкранный оверлей с лупой."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QWidget

from .theme import PALETTE

#: во сколько раз лупа увеличивает изображение
ZOOM = 8
#: размер окна лупы в пикселях экрана
LOUPE_SIZE = 132


def virtual_geometry() -> QRect:
    """Прямоугольник, покрывающий все мониторы."""
    rect = QRect()
    for screen in QGuiApplication.screens():
        rect = rect.united(screen.geometry())
    return rect if not rect.isEmpty() else QRect(0, 0, 1920, 1080)


def grab_desktop(rect: QRect) -> Optional[QPixmap]:
    """Снимок рабочего стола. Может быть недоступен (например, Wayland)."""
    try:
        combined = QPixmap(rect.size())
        combined.fill(Qt.GlobalColor.transparent)
        painter = QPainter(combined)
        captured = False
        for screen in QGuiApplication.screens():
            shot = screen.grabWindow(0)
            if shot.isNull():
                continue
            geometry = screen.geometry()
            painter.drawPixmap(geometry.topLeft() - rect.topLeft(), shot)
            captured = True
        painter.end()
        return combined if captured else None
    except Exception:
        return None


class PickerOverlay(QWidget):
    """Полупрозрачный слой поверх экрана: щелчок задаёт координаты."""

    picked = Signal(int, int)
    cancelled = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        # без этого окно было бы сплошным и закрывало бы экран, который выбираем
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.BlankCursor)
        self.setMouseTracking(True)
        self._rect = virtual_geometry()
        self._snapshot: Optional[QPixmap] = None
        self._pos = QPoint(self._rect.center())

    # ------------------------------------------------------------- запуск
    def start(self) -> None:
        self._rect = virtual_geometry()
        self._snapshot = grab_desktop(self._rect)
        self.setGeometry(self._rect)
        cursor = QCursor.pos()
        self._pos = cursor if self._rect.contains(cursor) else self._rect.center()
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    @property
    def point(self) -> tuple[int, int]:
        return self._pos.x(), self._pos.y()

    # -------------------------------------------------------------- ввод
    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._pos = event.globalPosition().toPoint()
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._pos = event.globalPosition().toPoint()
            self._finish()
        else:
            self._cancel()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        deltas = {
            Qt.Key.Key_Left: (-step, 0),
            Qt.Key.Key_Right: (step, 0),
            Qt.Key.Key_Up: (0, -step),
            Qt.Key.Key_Down: (0, step),
        }
        if key in deltas:
            dx, dy = deltas[key]
            self._pos = QPoint(self._pos.x() + dx, self._pos.y() + dy)
            QCursor.setPos(self._pos)
            self.update()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._finish()
        elif key == Qt.Key.Key_Escape:
            self._cancel()

    def _finish(self) -> None:
        self.hide()
        self.picked.emit(self._pos.x(), self._pos.y())

    def _cancel(self) -> None:
        self.hide()
        self.cancelled.emit()

    # ---------------------------------------------------------- отрисовка
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        local = self._pos - self._rect.topLeft()

        # снимок экрана как фон: так изображение не «дрожит» и совпадает с лупой
        if self._snapshot is not None:
            painter.drawPixmap(0, 0, self._snapshot)
        painter.fillRect(self.rect(), QColor(8, 10, 16, 90))

        pen = QPen(QColor(PALETTE.accent))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawLine(0, local.y(), self.width(), local.y())
        painter.drawLine(local.x(), 0, local.x(), self.height())

        self._draw_loupe(painter, local)
        self._draw_badge(painter, local)
        painter.end()

    def _draw_loupe(self, painter: QPainter, local: QPoint) -> None:
        if self._snapshot is None:
            return
        size = LOUPE_SIZE
        offset = 26
        x = local.x() + offset
        y = local.y() + offset
        if x + size > self.width():
            x = local.x() - offset - size
        if y + size > self.height():
            y = local.y() - offset - size

        span = max(2, size // ZOOM)
        source = QRect(local.x() - span // 2, local.y() - span // 2, span, span)
        target = QRect(x, y, size, size)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.fillRect(target, QColor(PALETTE.bg))
        painter.drawPixmap(target, self._snapshot, source)

        grid = QPen(QColor(255, 255, 255, 28))
        painter.setPen(grid)
        step = size / span
        for i in range(1, span):
            painter.drawLine(int(x + i * step), y, int(x + i * step), y + size)
            painter.drawLine(x, int(y + i * step), x + size, int(y + i * step))

        center = QPen(QColor(PALETTE.danger), 1.5)
        painter.setPen(center)
        cx = x + size / 2
        cy = y + size / 2
        painter.drawRect(QRectF(cx - step / 2, cy - step / 2, step, step))

        painter.setPen(QPen(QColor(PALETTE.accent), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(target), 10, 10)
        painter.restore()

    def _draw_badge(self, painter: QPainter, local: QPoint) -> None:
        text = f"X: {self._pos.x()}   Y: {self._pos.y()}"
        hint = "клик — выбрать · стрелки — точнее · Esc — отмена"
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        width = max(metrics.horizontalAdvance(text), metrics.horizontalAdvance(hint)) + 24
        height = 54
        x = min(max(8, local.x() - width // 2), self.width() - width - 8)
        y = local.y() - height - 34
        if y < 8:
            y = min(local.y() + LOUPE_SIZE + 46, self.height() - height - 8)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(16, 18, 25, 235))
        painter.drawRoundedRect(QRectF(x, y, width, height), 10, 10)
        painter.setPen(QColor(PALETTE.text))
        painter.drawText(QRect(x, y + 6, width, 20), Qt.AlignmentFlag.AlignCenter, text)
        font.setBold(False)
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(QColor(PALETTE.muted))
        painter.drawText(QRect(x, y + 28, width, 18), Qt.AlignmentFlag.AlignCenter, hint)
