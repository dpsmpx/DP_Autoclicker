"""Страница «Точки»: удобная настройка мест нажатия."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.models import Point, ValidationError
from ...core.script import ast_nodes
from ..icons import icon
from ..state import AppState
from ..theme import PALETTE, POINT_COLORS
from ..widgets.common import Card, hint_label, text_button, tool_button

SHAPE_LABELS = [("", "форма: авто"), ("circle", "круг"), ("square", "квадрат"), ("gauss", "гаусс")]


class PointsPage(QWidget):
    """Список точек и панель свойств выбранной точки."""

    #: попросить главное окно открыть прицел выбора координат
    pickRequested = Signal(object)  # Point | None — None означает «новая точка»

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        list_card = Card("Точки нажатия")
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self.pick_button = text_button(
            "Указать на экране", "primary", "target", self._pick_new, icon_color="#0B1020"
        )
        self.pick_button.setToolTip("Свернуть окно и выбрать точку прицелом")
        toolbar.addWidget(self.pick_button, 1)
        toolbar.addWidget(tool_button("plus", "Добавить точку по координатам", self._add_manual))
        toolbar.addWidget(tool_button("copy", "Дублировать", self._duplicate))
        toolbar.addWidget(tool_button("up", "Выше", lambda: self._move(-1)))
        toolbar.addWidget(tool_button("down", "Ниже", lambda: self._move(1)))
        toolbar.addWidget(tool_button("trash", "Удалить", self._delete, PALETTE.danger))
        list_card.body().addLayout(toolbar)

        self.list = QListWidget()
        self.list.setIconSize(QSize(18, 18))
        self.list.setAlternatingRowColors(True)
        self.list.setMinimumHeight(150)
        self.list.currentRowChanged.connect(lambda _: self._load_selected())
        self.list.itemDoubleClicked.connect(lambda _: self._pick_existing())
        list_card.add(self.list)
        list_card.add(
            hint_label(
                "Двойной клик по точке — заново указать её положение прицелом. "
                "Имя точки используется в алгоритме."
            )
        )
        root.addWidget(list_card, 1)

        self.editor = Card("Свойства точки")
        form = self.editor.body()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Имя точки, например Кнопка_ОК")
        self.name_edit.editingFinished.connect(self._apply_name)
        form.addWidget(QLabel("Имя"))
        form.addWidget(self.name_edit)

        coords = QHBoxLayout()
        coords.setSpacing(8)
        self.x_spin = QSpinBox()
        self.y_spin = QSpinBox()
        for spin, label in ((self.x_spin, "X"), (self.y_spin, "Y")):
            spin.setRange(-32000, 32000)
            spin.setPrefix(f"{label}: ")
            spin.valueChanged.connect(self._apply_coords)
            coords.addWidget(spin, 1)
        self.pick_again = tool_button("target", "Указать прицелом", self._pick_existing, PALETTE.accent)
        coords.addWidget(self.pick_again)
        form.addLayout(coords)

        extras = QHBoxLayout()
        extras.setSpacing(8)
        self.radius_spin = QDoubleSpinBox()
        self.radius_spin.setRange(0.0, 400.0)
        self.radius_spin.setDecimals(1)
        self.radius_spin.setSuffix(" px")
        self.radius_spin.setPrefix("разброс: ")
        self.radius_spin.setToolTip(
            "Личный радиус разброса точки. 0 — брать значение из настроек рандомизации."
        )
        self.radius_spin.valueChanged.connect(self._apply_extras)
        extras.addWidget(self.radius_spin, 1)

        self.shape_combo = QComboBox()
        for value, label in SHAPE_LABELS:
            self.shape_combo.addItem(label, value)
        self.shape_combo.setToolTip(
            "Форма области разброса. «Авто» — как задано в настройках рандомизации."
        )
        self.shape_combo.currentIndexChanged.connect(self._apply_extras)
        extras.addWidget(self.shape_combo, 1)

        self.color_button = text_button("Цвет", "", "point", self._pick_color)
        extras.addWidget(self.color_button)
        form.addLayout(extras)

        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("Заметка: что здесь находится")
        self.note_edit.editingFinished.connect(self._apply_extras)
        form.addWidget(self.note_edit)

        self.error_label = QLabel()
        self.error_label.setStyleSheet(f"color: {PALETTE.danger};")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        form.addWidget(self.error_label)

        root.addWidget(self.editor)

        state.pointsChanged.connect(self.refresh)
        state.presetReplaced.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------ служебное
    @property
    def points(self) -> list[Point]:
        return self.state.preset.points

    def current(self) -> Optional[Point]:
        row = self.list.currentRow()
        if 0 <= row < len(self.points):
            return self.points[row]
        return None

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(bool(message))

    def refresh(self) -> None:
        row = self.list.currentRow()
        self._loading = True
        self.list.clear()
        for point in self.points:
            item = QListWidgetItem(icon("point", point.color, 18), self._label(point))
            item.setToolTip(point.note or "Без заметки")
            self.list.addItem(item)
        self._loading = False
        if self.points:
            self.list.setCurrentRow(min(max(0, row), len(self.points) - 1))
        else:
            self._load_selected()

    @staticmethod
    def _label(point: Point) -> str:
        extra = f"  ±{point.radius:g}px" if point.radius else ""
        return f"{point.name}   ({point.x}, {point.y}){extra}"

    def _load_selected(self) -> None:
        point = self.current()
        self.editor.setEnabled(point is not None)
        self._show_error("")
        if point is None:
            self._loading = True
            self.name_edit.clear()
            self.note_edit.clear()
            self._loading = False
            return
        self._loading = True
        self.name_edit.setText(point.name)
        self.x_spin.setValue(point.x)
        self.y_spin.setValue(point.y)
        self.radius_spin.setValue(point.radius)
        index = self.shape_combo.findData(point.shape)
        self.shape_combo.setCurrentIndex(max(0, index))
        self.note_edit.setText(point.note)
        self.color_button.setIcon(icon("point", point.color, 18))
        self._loading = False

    # ---------------------------------------------------------- изменения
    def _apply_name(self) -> None:
        point = self.current()
        if point is None or self._loading:
            return
        new_name = self.name_edit.text().strip()
        if not new_name or new_name == point.name:
            self.name_edit.setText(point.name)
            return
        previous = point.name
        try:
            self.state.preset.rename_point(point, new_name)
        except ValidationError as exc:
            self._show_error(str(exc))
            self.name_edit.setText(point.name)
            return
        # то же переименование в дереве алгоритма, чтобы блоки не «потеряли» точку
        ast_nodes.rename_point(self.state.program, previous, new_name)
        self._show_error("")
        self.state.notify_points()
        self.state.programChanged.emit("points")

    def _apply_coords(self) -> None:
        point = self.current()
        if point is None or self._loading:
            return
        point.x = self.x_spin.value()
        point.y = self.y_spin.value()
        self._refresh_current_item(point)
        self.state.mark_dirty()

    def _apply_extras(self) -> None:
        point = self.current()
        if point is None or self._loading:
            return
        point.radius = self.radius_spin.value()
        point.shape = self.shape_combo.currentData() or ""
        point.note = self.note_edit.text().strip()
        self._refresh_current_item(point)
        self.state.mark_dirty()

    def _refresh_current_item(self, point: Point) -> None:
        item = self.list.currentItem()
        if item is not None:
            item.setText(self._label(point))
            item.setIcon(icon("point", point.color, 18))
            item.setToolTip(point.note or "Без заметки")

    def _pick_color(self) -> None:
        point = self.current()
        if point is None:
            return
        color = QColorDialog.getColor(QColor(point.color), self, "Цвет точки")
        if color.isValid():
            point.color = color.name()
            self._refresh_current_item(point)
            self.state.mark_dirty()

    # -------------------------------------------------------------- список
    def _next_color(self) -> str:
        return POINT_COLORS[len(self.points) % len(POINT_COLORS)]

    def add_point(self, x: int, y: int) -> Point:
        """Добавляет точку (вызывается и из прицела)."""
        point = self.state.preset.add_point(x, y)
        point.color = self._next_color()
        self.state.notify_points()
        self.list.setCurrentRow(len(self.points) - 1)
        return point

    def _add_manual(self) -> None:
        width, height = self.state.screen_size
        self.add_point(width // 2, height // 2)

    def _pick_new(self) -> None:
        self.pickRequested.emit(None)

    def _pick_existing(self) -> None:
        point = self.current()
        if point is not None:
            self.pickRequested.emit(point)

    def _duplicate(self) -> None:
        point = self.current()
        if point is None:
            return
        clone = point.copy()
        clone.name = self.state.preset.unique_name(point.name.rstrip("0123456789_") or "Точка")
        clone.x += 20
        clone.y += 20
        self.points.append(clone)
        self.state.notify_points()
        self.list.setCurrentRow(len(self.points) - 1)

    def _delete(self) -> None:
        point = self.current()
        if point is None:
            return
        self.state.preset.remove_point(point)
        self.state.notify_points()

    def _move(self, delta: int) -> None:
        row = self.list.currentRow()
        target = row + delta
        if row < 0 or not (0 <= target < len(self.points)):
            return
        self.points[row], self.points[target] = self.points[target], self.points[row]
        self.state.notify_points()
        self.list.setCurrentRow(target)
