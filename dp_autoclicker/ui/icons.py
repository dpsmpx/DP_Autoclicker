"""Векторные иконки, нарисованные средствами Qt (без внешних файлов)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from .theme import PALETTE

_GRID = 24.0


def _pen(color: QColor, width: float = 2.0) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _draw(name: str, painter: QPainter, color: QColor) -> None:
    painter.setPen(_pen(color))
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if name == "play":
        path = QPainterPath(QPointF(8, 5))
        path.lineTo(19, 12)
        path.lineTo(8, 19)
        path.closeSubpath()
        painter.setBrush(color)
        painter.drawPath(path)
    elif name == "stop":
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(6, 6, 12, 12), 2.5, 2.5)
    elif name == "pause":
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(7, 5, 3.6, 14), 1.6, 1.6)
        painter.drawRoundedRect(QRectF(13.4, 5, 3.6, 14), 1.6, 1.6)
    elif name == "target":
        painter.drawEllipse(QPointF(12, 12), 7.5, 7.5)
        painter.drawEllipse(QPointF(12, 12), 2.4, 2.4)
        painter.drawLine(QPointF(12, 1.5), QPointF(12, 5))
        painter.drawLine(QPointF(12, 19), QPointF(12, 22.5))
        painter.drawLine(QPointF(1.5, 12), QPointF(5, 12))
        painter.drawLine(QPointF(19, 12), QPointF(22.5, 12))
    elif name == "blocks":
        painter.drawRoundedRect(QRectF(4, 4, 16, 5), 2, 2)
        painter.drawRoundedRect(QRectF(7, 12, 13, 5), 2, 2)
        painter.drawLine(QPointF(4, 9), QPointF(4, 14.5))
        painter.drawLine(QPointF(4, 14.5), QPointF(7, 14.5))
    elif name == "code":
        painter.drawPolyline([QPointF(9, 7), QPointF(4, 12), QPointF(9, 17)])
        painter.drawPolyline([QPointF(15, 7), QPointF(20, 12), QPointF(15, 17)])
    elif name == "gear":
        painter.drawEllipse(QPointF(12, 12), 3.2, 3.2)
        painter.drawEllipse(QPointF(12, 12), 7.4, 7.4)
        for i in range(6):
            painter.save()
            painter.translate(12, 12)
            painter.rotate(i * 60)
            painter.drawLine(QPointF(0, -7.4), QPointF(0, -9.6))
            painter.restore()
    elif name == "list":
        for y in (7, 12, 17):
            painter.drawLine(QPointF(9, y), QPointF(19, y))
            painter.drawPoint(QPointF(5, y))
            painter.drawEllipse(QPointF(5, y), 1.1, 1.1)
    elif name == "plus":
        painter.drawLine(QPointF(12, 6), QPointF(12, 18))
        painter.drawLine(QPointF(6, 12), QPointF(18, 12))
    elif name == "minus":
        painter.drawLine(QPointF(6, 12), QPointF(18, 12))
    elif name == "trash":
        painter.drawLine(QPointF(4.5, 7), QPointF(19.5, 7))
        painter.drawPolyline(
            [QPointF(6.5, 7), QPointF(7.5, 19.5), QPointF(16.5, 19.5), QPointF(17.5, 7)]
        )
        painter.drawPolyline([QPointF(9.5, 7), QPointF(9.5, 4.5), QPointF(14.5, 4.5), QPointF(14.5, 7)])
    elif name == "copy":
        painter.drawRoundedRect(QRectF(8, 8, 12, 12), 2.5, 2.5)
        painter.drawPolyline([QPointF(16, 5), QPointF(4.5, 5), QPointF(4.5, 16)])
    elif name == "up":
        painter.drawPolyline([QPointF(6, 14), QPointF(12, 8), QPointF(18, 14)])
    elif name == "down":
        painter.drawPolyline([QPointF(6, 10), QPointF(12, 16), QPointF(18, 10)])
    elif name == "left":
        painter.drawPolyline([QPointF(14, 6), QPointF(8, 12), QPointF(14, 18)])
    elif name == "right":
        painter.drawPolyline([QPointF(10, 6), QPointF(16, 12), QPointF(10, 18)])
    elif name == "save":
        painter.drawRoundedRect(QRectF(4.5, 4.5, 15, 15), 2.5, 2.5)
        painter.drawRect(QRectF(8.5, 4.5, 7, 5))
        painter.drawRect(QRectF(8, 13, 8, 6.5))
    elif name == "open":
        painter.drawPolyline(
            [QPointF(4, 18.5), QPointF(4, 6), QPointF(10, 6), QPointF(12, 8.5), QPointF(20, 8.5)]
        )
        painter.drawPolyline([QPointF(4, 18.5), QPointF(20, 18.5), QPointF(20, 8.5)])
    elif name == "export":
        painter.drawPolyline([QPointF(12, 15), QPointF(12, 4), QPointF(12, 4)])
        painter.drawPolyline([QPointF(8, 8), QPointF(12, 4), QPointF(16, 8)])
        painter.drawPolyline([QPointF(5, 14), QPointF(5, 20), QPointF(19, 20), QPointF(19, 14)])
    elif name == "import":
        painter.drawLine(QPointF(12, 4), QPointF(12, 15))
        painter.drawPolyline([QPointF(8, 11), QPointF(12, 15), QPointF(16, 11)])
        painter.drawPolyline([QPointF(5, 14), QPointF(5, 20), QPointF(19, 20), QPointF(19, 14)])
    elif name == "pin":
        painter.drawPolyline(
            [QPointF(9, 3.5), QPointF(15, 3.5), QPointF(13.5, 10), QPointF(17, 13.5),
             QPointF(7, 13.5), QPointF(10.5, 10), QPointF(9, 3.5)]
        )
        painter.drawLine(QPointF(12, 13.5), QPointF(12, 20.5))
    elif name == "close":
        painter.drawLine(QPointF(7, 7), QPointF(17, 17))
        painter.drawLine(QPointF(17, 7), QPointF(7, 17))
    elif name == "collapse":
        painter.drawLine(QPointF(6, 12), QPointF(18, 12))
        painter.drawPolyline([QPointF(9, 8), QPointF(12, 5), QPointF(15, 8)])
    elif name == "expand":
        painter.drawLine(QPointF(6, 12), QPointF(18, 12))
        painter.drawPolyline([QPointF(9, 16), QPointF(12, 19), QPointF(15, 16)])
    elif name == "dice":
        painter.drawRoundedRect(QRectF(4.5, 4.5, 15, 15), 3.5, 3.5)
        painter.setBrush(color)
        for cx, cy in ((9, 9), (15, 15), (12, 12)):
            painter.drawEllipse(QPointF(cx, cy), 1.4, 1.4)
    elif name == "eye":
        path = QPainterPath(QPointF(3, 12))
        path.quadTo(QPointF(12, 3.5), QPointF(21, 12))
        path.quadTo(QPointF(12, 20.5), QPointF(3, 12))
        painter.drawPath(path)
        painter.drawEllipse(QPointF(12, 12), 2.6, 2.6)
    elif name == "wand":
        painter.drawLine(QPointF(5, 19), QPointF(16, 8))
        painter.drawLine(QPointF(18, 4), QPointF(18, 8))
        painter.drawLine(QPointF(16, 6), QPointF(20, 6))
        painter.drawLine(QPointF(8, 5), QPointF(8, 8))
        painter.drawLine(QPointF(6.5, 6.5), QPointF(9.5, 6.5))
    elif name == "check":
        painter.drawPolyline([QPointF(5, 12.5), QPointF(10, 17.5), QPointF(19, 6.5)])
    elif name == "warning":
        painter.drawPolyline([QPointF(12, 4), QPointF(21, 19.5), QPointF(3, 19.5), QPointF(12, 4)])
        painter.drawLine(QPointF(12, 10), QPointF(12, 14.5))
        painter.drawEllipse(QPointF(12, 17), 0.7, 0.7)
    elif name == "point":
        painter.setBrush(color)
        painter.drawEllipse(QPointF(12, 12), 5.5, 5.5)
    else:
        painter.drawEllipse(QPointF(12, 12), 6, 6)


def pixmap(name: str, color: str = PALETTE.text, size: int = 20) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale(size / _GRID, size / _GRID)
    _draw(name, painter, QColor(color))
    painter.end()
    return pix


def icon(name: str, color: str = PALETTE.text, size: int = 20) -> QIcon:
    return QIcon(pixmap(name, color, size))
