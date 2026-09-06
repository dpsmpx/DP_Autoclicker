"""Редакторы значений для панели свойств блока.

Каждый редактор умеет две вещи: показать значение по-человечески
(поля, единицы, выпадающие списки) и вернуть его как узел выражения.
Для сложных случаев есть режим «формула», где можно написать выражение.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QStackedWidget,
    QToolButton,
    QWidget,
)

from ...core.script import ast_nodes as ast
from ...core.script.errors import ScriptError
from ...core.script.parser import parse_expression
from ...core.script.printer import Printer
from ..icons import icon
from ..theme import PALETTE

BUTTON_LABELS = (("left", "левая"), ("right", "правая"), ("middle", "средняя"))


class ValueEditor(QWidget):
    """Общая часть: переключатель «простое значение / формула»."""

    changed = Signal()

    def __init__(self, dialect: str = "ru", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.dialect = dialect
        self._blocked = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.stack = QStackedWidget()
        self.simple = QWidget()
        self.simple_layout = QHBoxLayout(self.simple)
        self.simple_layout.setContentsMargins(0, 0, 0, 0)
        self.simple_layout.setSpacing(6)
        self.formula = QLineEdit()
        self.formula.setPlaceholderText("выражение, например 100мс * 2")
        self.formula.textChanged.connect(self._on_formula)
        self.stack.addWidget(self.simple)
        self.stack.addWidget(self.formula)
        layout.addWidget(self.stack, 1)

        self.mode_button = QToolButton()
        self.mode_button.setText("fx")
        self.mode_button.setCheckable(True)
        self.mode_button.setToolTip("Режим формулы: задать значение выражением")
        self.mode_button.setFixedSize(30, 28)
        self.mode_button.toggled.connect(self._on_mode)
        layout.addWidget(self.mode_button)

    # ------------------------------------------------------------ поведение
    def _on_mode(self, formula: bool) -> None:
        if formula and not self._blocked:
            node = self._simple_value()
            if node is not None:
                self.formula.blockSignals(True)
                self.formula.setText(Printer(self.dialect).expr(node))
                self.formula.blockSignals(False)
        self.stack.setCurrentIndex(1 if formula else 0)
        if not self._blocked:
            self.changed.emit()

    def _on_formula(self, text: str) -> None:
        valid = True
        if text.strip():
            try:
                parse_expression(text)
            except ScriptError:
                valid = False
        self.formula.setStyleSheet("" if valid else f"border-color: {PALETTE.danger};")
        if valid and not self._blocked:
            self.changed.emit()

    def _simple_value(self) -> Optional[ast.Expr]:  # pragma: no cover - переопределяется
        return None

    def value(self) -> Optional[ast.Expr]:
        if self.mode_button.isChecked():
            text = self.formula.text().strip()
            if not text:
                return None
            try:
                return parse_expression(text)
            except ScriptError:
                return None
        return self._simple_value()

    def set_value(self, node: Optional[ast.Expr]) -> None:
        self._blocked = True
        try:
            simple = self._load_simple(node)
            self.mode_button.setChecked(not simple)
            self.stack.setCurrentIndex(0 if simple else 1)
            if not simple and node is not None:
                self.formula.setText(Printer(self.dialect).expr(node))
        finally:
            self._blocked = False

    def _load_simple(self, node: Optional[ast.Expr]) -> bool:  # pragma: no cover
        return True


class DurationEditor(ValueEditor):
    """Длительность: значение, единица и необязательный случайный диапазон."""

    def __init__(self, dialect: str = "ru", parent: Optional[QWidget] = None) -> None:
        super().__init__(dialect, parent)
        self.from_spin = QDoubleSpinBox()
        self.to_spin = QDoubleSpinBox()
        for spin in (self.from_spin, self.to_spin):
            spin.setRange(0.0, 3_600_000.0)
            spin.setDecimals(0)
            spin.setSingleStep(50)
            spin.setMinimumWidth(64)
            spin.valueChanged.connect(self._emit)
        self.unit = QComboBox()
        self.unit.addItem("мс", 0.001)
        self.unit.addItem("с", 1.0)
        self.unit.currentIndexChanged.connect(self._on_unit)
        self.range_box = QToolButton()
        self.range_box.setText("a..b")
        self.range_box.setCheckable(True)
        self.range_box.setFixedSize(44, 28)
        self.range_box.setToolTip("Случайное значение в заданных пределах")
        self.range_box.toggled.connect(self._on_range)

        self.dash = QLabel("-")
        self.simple_layout.addWidget(self.from_spin, 1)
        self.simple_layout.addWidget(self.dash)
        self.simple_layout.addWidget(self.to_spin, 1)
        self.simple_layout.addWidget(self.unit)
        self.simple_layout.addWidget(self.range_box)
        self._set_range_visible(False)

    def _set_range_visible(self, visible: bool) -> None:
        self.dash.setVisible(visible)
        self.to_spin.setVisible(visible)

    def _on_range(self, checked: bool) -> None:
        self._set_range_visible(checked)
        if checked and self.to_spin.value() <= self.from_spin.value():
            self.to_spin.setValue(self.from_spin.value() * 2 or 100)
        self._emit()

    def _on_unit(self) -> None:
        factor = self.unit.currentData()
        decimals = 0 if factor == 0.001 else 2
        step = 50 if factor == 0.001 else 0.5
        for spin in (self.from_spin, self.to_spin):
            spin.setDecimals(decimals)
            spin.setSingleStep(step)
        self._emit()

    def _emit(self) -> None:
        if not self._blocked:
            self.changed.emit()

    def _seconds(self, spin: QDoubleSpinBox) -> float:
        return spin.value() * float(self.unit.currentData())

    def _simple_value(self) -> Optional[ast.Expr]:
        low = ast.Literal(value=self._seconds(self.from_spin), kind="duration")
        if not self.range_box.isChecked():
            return low
        high = ast.Literal(value=self._seconds(self.to_spin), kind="duration")
        return ast.Range(low=low, high=high)

    def _load_simple(self, node: Optional[ast.Expr]) -> bool:
        def is_duration(candidate) -> bool:
            return isinstance(candidate, ast.Literal) and candidate.kind == "duration"

        if node is None:
            self.range_box.setChecked(False)
            self.from_spin.setValue(0)
            return True
        if is_duration(node):
            self._fill(float(node.value), None)
            return True
        if isinstance(node, ast.Range) and is_duration(node.low) and is_duration(node.high):
            self._fill(float(node.low.value), float(node.high.value))
            return True
        return False

    def _fill(self, low: float, high: Optional[float]) -> None:
        use_seconds = low >= 1.0 and (high is None or high >= 1.0)
        self.unit.setCurrentIndex(1 if use_seconds else 0)
        self._on_unit()
        factor = float(self.unit.currentData())
        self.from_spin.setValue(low / factor)
        self.range_box.setChecked(high is not None)
        self._set_range_visible(high is not None)
        if high is not None:
            self.to_spin.setValue(high / factor)


class NumberEditor(ValueEditor):
    """Обычное число."""

    def __init__(
        self,
        dialect: str = "ru",
        minimum: float = -99999.0,
        maximum: float = 999999.0,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(dialect, parent)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(minimum, maximum)
        self.spin.setDecimals(0)
        self.spin.valueChanged.connect(lambda _: None if self._blocked else self.changed.emit())
        self.simple_layout.addWidget(self.spin, 1)

    def _simple_value(self) -> Optional[ast.Expr]:
        return ast.Literal(value=float(self.spin.value()), kind="number")

    def _load_simple(self, node: Optional[ast.Expr]) -> bool:
        if node is None:
            self.spin.setValue(0)
            return True
        if isinstance(node, ast.Literal) and node.kind == "number":
            self.spin.setValue(float(node.value))
            return True
        return False


class ExprEditor(QWidget):
    """Свободное выражение с проверкой на лету."""

    changed = Signal()

    def __init__(
        self, dialect: str = "ru", placeholder: str = "", parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.dialect = dialect
        self._blocked = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder or "например: шанс(30%)")
        self.edit.textChanged.connect(self._on_text)
        layout.addWidget(self.edit, 1)

    def _on_text(self, text: str) -> None:
        valid = True
        if text.strip():
            try:
                parse_expression(text)
            except ScriptError:
                valid = False
        self.edit.setStyleSheet("" if valid else f"border-color: {PALETTE.danger};")
        if valid and not self._blocked:
            self.changed.emit()

    def value(self) -> Optional[ast.Expr]:
        text = self.edit.text().strip()
        if not text:
            return None
        try:
            return parse_expression(text)
        except ScriptError:
            return None

    def set_value(self, node: Optional[ast.Expr]) -> None:
        self._blocked = True
        self.edit.setText(Printer(self.dialect).expr(node) if node is not None else "")
        self._blocked = False


class ButtonEditor(QComboBox):
    """Выбор кнопки мыши."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        for value, label in BUTTON_LABELS:
            self.addItem(label, value)

    def value(self) -> str:
        return str(self.currentData())

    def set_value(self, button: str) -> None:
        index = self.findData(button)
        self.setCurrentIndex(max(0, index))


class TargetEditor(QWidget):
    """Точка из списка либо явные координаты."""

    changed = Signal()
    pickRequested = Signal()

    COORDS = " coords"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._blocked = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.combo = QComboBox()
        self.combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.combo.setMinimumContentsLength(6)
        self.combo.currentIndexChanged.connect(self._on_combo)
        layout.addWidget(self.combo, 1)

        self.x_spin = QDoubleSpinBox()
        self.y_spin = QDoubleSpinBox()
        for spin, prefix in ((self.x_spin, "X: "), (self.y_spin, "Y: ")):
            spin.setMinimumWidth(78)
            spin.setRange(-32000, 32000)
            spin.setDecimals(0)
            spin.setPrefix(prefix)
            spin.valueChanged.connect(lambda _: None if self._blocked else self.changed.emit())
            layout.addWidget(spin)

        self.pick_button = QToolButton()
        self.pick_button.setIcon(icon("target", PALETTE.accent, 18))
        self.pick_button.setToolTip("Указать координаты прицелом")
        self.pick_button.setFixedSize(30, 28)
        self.pick_button.clicked.connect(self.pickRequested)
        layout.addWidget(self.pick_button)
        self._set_coords_visible(False)

    def _set_coords_visible(self, visible: bool) -> None:
        self.x_spin.setVisible(visible)
        self.y_spin.setVisible(visible)
        self.pick_button.setVisible(visible)

    def set_points(self, names: list[str]) -> None:
        current = self.combo.currentData()
        self._blocked = True
        self.combo.clear()
        for name in names:
            self.combo.addItem(name, name)
        self.combo.addItem("координаты...", self.COORDS)
        index = self.combo.findData(current)
        self.combo.setCurrentIndex(index if index >= 0 else 0)
        self._set_coords_visible(self.combo.currentData() == self.COORDS)
        self._blocked = False

    def _on_combo(self) -> None:
        self._set_coords_visible(self.combo.currentData() == self.COORDS)
        if not self._blocked:
            self.changed.emit()

    def set_coords(self, x: int, y: int) -> None:
        self._blocked = True
        index = self.combo.findData(self.COORDS)
        if index >= 0:
            self.combo.setCurrentIndex(index)
        self._set_coords_visible(True)
        self.x_spin.setValue(x)
        self.y_spin.setValue(y)
        self._blocked = False
        self.changed.emit()

    def value(self) -> ast.Target:
        data = self.combo.currentData()
        if data == self.COORDS or data is None:
            return ast.Target(
                x=ast.Literal(value=float(self.x_spin.value()), kind="number"),
                y=ast.Literal(value=float(self.y_spin.value()), kind="number"),
            )
        return ast.Target(point=str(data))

    def set_value(self, target: Optional[ast.Target]) -> None:
        self._blocked = True
        try:
            if target is not None and target.is_point:
                index = self.combo.findData(target.point)
                if index < 0:
                    self.combo.insertItem(0, target.point, target.point)
                    index = 0
                self.combo.setCurrentIndex(index)
                self._set_coords_visible(False)
                return
            index = self.combo.findData(self.COORDS)
            if index >= 0:
                self.combo.setCurrentIndex(index)
            self._set_coords_visible(True)
            if target is not None:
                for node, spin in ((target.x, self.x_spin), (target.y, self.y_spin)):
                    if isinstance(node, ast.Literal):
                        spin.setValue(float(node.value))
        finally:
            self._blocked = False
