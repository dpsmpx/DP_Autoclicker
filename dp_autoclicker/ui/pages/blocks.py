"""Страница «Алгоритм»: визуальный конструктор блоков.

Дерево блоков — это то же самое дерево, что и текст скрипта. Любое
изменение здесь сразу отражается на вкладке «Скрипт» и наоборот.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QScrollArea,
    QSplitter,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.script import ast_nodes as ast
from ...core.script.errors import ScriptError
from ...core.script.printer import stmt_to_source
from ...core.runtime.interpreter import collect
from ..blocks_meta import BlockSpec, CATEGORIES, FieldSpec, by_category, spec_for
from ..icons import icon
from ..state import AppState
from ..theme import BLOCK_COLORS, PALETTE
from ..widgets.common import Card, hint_label, tool_button
from ..widgets.value_editors import (
    ButtonEditor,
    DurationEditor,
    ExprEditor,
    NumberEditor,
    TargetEditor,
)

NODE_ROLE = int(Qt.ItemDataRole.UserRole)
KIND_ROLE = int(Qt.ItemDataRole.UserRole) + 1
SLOT_ROLE = int(Qt.ItemDataRole.UserRole) + 2

#: сколько действий максимум считаем при оценке алгоритма
ESTIMATE_LIMIT = 2000


class BlocksPage(QWidget):
    """Дерево блоков плюс панель свойств выбранного блока."""

    #: запрос координат прицелом; аргумент — функция-приёмник (x, y)
    pickRequested = Signal(object)

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._loading = False
        self._push_timer = QTimer(self)
        self._push_timer.setSingleShot(True)
        self._push_timer.setInterval(220)
        self._push_timer.timeout.connect(self._push)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        tree_card = Card("Алгоритм")
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.add_button = QToolButton()
        self.add_button.setText("  Добавить блок")
        self.add_button.setIcon(icon("plus", "#0B1020", 18))
        self.add_button.setIconSize(QSize(18, 18))
        self.add_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.add_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.setStyleSheet(
            f"QToolButton {{ background: {PALETTE.accent}; color: #0B1020;"
            f" border-radius: 9px; padding: 6px 12px; font-weight: 600; }}"
            f"QToolButton::menu-indicator {{ image: none; }}"
        )
        self.add_button.setMenu(self._build_add_menu())
        toolbar.addWidget(self.add_button, 1)
        toolbar.addWidget(tool_button("copy", "Дублировать блок", self._duplicate))
        toolbar.addWidget(tool_button("up", "Переместить выше", lambda: self._move(-1)))
        toolbar.addWidget(tool_button("down", "Переместить ниже", lambda: self._move(1)))
        toolbar.addWidget(tool_button("left", "Вынести из блока", self._outdent))
        toolbar.addWidget(tool_button("trash", "Удалить блок", self._delete, PALETTE.danger))
        tree_card.body().addLayout(toolbar)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(18, 18))
        self.tree.setIndentation(18)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setExpandsOnDoubleClick(True)
        self.tree.setMinimumHeight(170)
        palette = self.tree.palette()
        palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 0, 0, 0))
        self.tree.setPalette(palette)
        self.tree.currentItemChanged.connect(lambda *_: self._show_properties())
        self.tree.model().rowsMoved.connect(self._on_rows_moved)
        tree_card.add(self.tree)

        self.empty_hint = hint_label(
            "Соберите алгоритм из блоков: перетаскивайте их мышью, вкладывайте "
            "друг в друга. Тот же алгоритм текстом — на вкладке «Скрипт»."
        )
        tree_card.add(self.empty_hint)

        self.props_card = Card("Свойства блока")
        self.props_scroll = QScrollArea()
        self.props_scroll.setWidgetResizable(True)
        self.props_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.props_host = QWidget()
        self.props_form = QFormLayout(self.props_host)
        self.props_form.setContentsMargins(0, 0, 0, 0)
        self.props_form.setSpacing(8)
        self.props_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.props_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.props_scroll.setWidget(self.props_host)
        self.props_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.props_scroll.setSizeAdjustPolicy(
            QScrollArea.SizeAdjustPolicy.AdjustToContents
        )
        self.props_scroll.setMinimumHeight(150)
        self.props_scroll.setMaximumHeight(260)
        self.props_card.add(self.props_scroll)
        self.props_card.setMinimumHeight(150)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(8)
        self.splitter.addWidget(tree_card)
        self.splitter.addWidget(self.props_card)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([280, 240])
        root.addWidget(self.splitter, 1)

        self.summary = QLabel()
        self.summary.setProperty("role", "hint")
        root.addWidget(self.summary)

        state.programChanged.connect(self._on_program_changed)
        state.presetReplaced.connect(self.reload)
        state.pointsChanged.connect(self._refresh_points)
        self.reload()

    # ------------------------------------------------------------ построение
    def _build_add_menu(self) -> QMenu:
        menu = QMenu(self)
        grouped = by_category()
        for category in CATEGORIES:
            specs = grouped.get(category) or []
            if not specs:
                continue
            submenu = menu.addMenu(category)
            for spec in specs:
                action = submenu.addAction(icon(spec.icon, spec.color, 18), spec.label)
                action.setToolTip(spec.hint)
                action.triggered.connect(lambda _=False, s=spec: self._add_block(s))
        return menu

    def reload(self) -> None:
        self._rebuild_tree()
        self._show_properties()
        self._update_summary()

    def _on_program_changed(self, origin: str) -> None:
        if origin == "blocks":
            self._update_summary()
            return
        self.reload()

    def _rebuild_tree(self, select_uid: str = "") -> None:
        self._loading = True
        expanded = self._expanded_uids()
        self.tree.clear()
        self._fill(self.tree.invisibleRootItem(), self.state.program)
        self.tree.expandAll()
        for item in self._all_items():
            node = item.data(0, NODE_ROLE)
            if expanded and isinstance(node, ast.Stmt) and node.uid not in expanded:
                item.setExpanded(False)
        self._loading = False
        self.empty_hint.setVisible(not self.state.program)
        if select_uid:
            self._select_uid(select_uid)

    def _fill(self, parent: QTreeWidgetItem, block: ast.Block) -> None:
        for stmt in block:
            item = self._make_item(stmt)
            parent.addChild(item)
            if isinstance(stmt, ast.If):
                for slot, title in (("body", "то"), ("orelse", "иначе")):
                    group = QTreeWidgetItem([title])
                    group.setData(0, KIND_ROLE, "group")
                    group.setData(0, SLOT_ROLE, slot)
                    group.setData(0, NODE_ROLE, stmt)
                    group.setForeground(0, Qt.GlobalColor.gray)
                    group.setFlags(
                        Qt.ItemFlag.ItemIsEnabled
                        | Qt.ItemFlag.ItemIsSelectable
                        | Qt.ItemFlag.ItemIsDropEnabled
                    )
                    item.addChild(group)
                    self._fill(group, getattr(stmt, slot))
            elif ast.is_container(stmt):
                self._fill(item, stmt.body)

    def _make_item(self, stmt: ast.Stmt) -> QTreeWidgetItem:
        spec = spec_for(stmt)
        item = QTreeWidgetItem([self._label(stmt)])
        item.setData(0, NODE_ROLE, stmt)
        item.setData(0, KIND_ROLE, "stmt")
        color = spec.color if spec else BLOCK_COLORS["action"]
        item.setIcon(0, icon(spec.icon if spec else "point", color, 18))
        flags = (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
        )
        if ast.is_container(stmt) and not isinstance(stmt, ast.If):
            flags |= Qt.ItemFlag.ItemIsDropEnabled
        item.setFlags(flags)
        if stmt.comment:
            item.setToolTip(0, stmt.comment)
        return item

    @staticmethod
    def _label(stmt: ast.Stmt) -> str:
        try:
            text = stmt_to_source(stmt)
        except Exception:  # pragma: no cover - защита от неполного узла
            text = type(stmt).__name__
        return text.rstrip(" {")

    # ------------------------------------------------------------ обход дерева
    def _all_items(self, parent: Optional[QTreeWidgetItem] = None) -> list[QTreeWidgetItem]:
        parent = parent or self.tree.invisibleRootItem()
        out: list[QTreeWidgetItem] = []
        for i in range(parent.childCount()):
            child = parent.child(i)
            out.append(child)
            out.extend(self._all_items(child))
        return out

    def _expanded_uids(self) -> set[str]:
        uids: set[str] = set()
        for item in self._all_items():
            node = item.data(0, NODE_ROLE)
            if item.isExpanded() and isinstance(node, ast.Stmt):
                uids.add(node.uid)
        return uids

    def _select_uid(self, uid: str) -> None:
        for item in self._all_items():
            node = item.data(0, NODE_ROLE)
            if item.data(0, KIND_ROLE) == "stmt" and isinstance(node, ast.Stmt) and node.uid == uid:
                self.tree.setCurrentItem(item)
                return

    def current_node(self) -> Optional[ast.Stmt]:
        item = self.tree.currentItem()
        if item is None or item.data(0, KIND_ROLE) != "stmt":
            return None
        node = item.data(0, NODE_ROLE)
        return node if isinstance(node, ast.Stmt) else None

    # ------------------------------------ дерево виджетов -> дерево программы
    def _collect(self, parent: Optional[QTreeWidgetItem] = None) -> ast.Block:
        parent = parent or self.tree.invisibleRootItem()
        block: ast.Block = []
        for i in range(parent.childCount()):
            item = parent.child(i)
            if item.data(0, KIND_ROLE) != "stmt":
                continue
            node = item.data(0, NODE_ROLE)
            if isinstance(node, ast.If):
                node.body, node.orelse = [], []
                for j in range(item.childCount()):
                    group = item.child(j)
                    if group.data(0, KIND_ROLE) == "group":
                        setattr(node, group.data(0, SLOT_ROLE), self._collect(group))
            elif ast.is_container(node):
                node.body = self._collect(item)
            block.append(node)
        return block

    def _on_rows_moved(self, *_args: Any) -> None:
        if self._loading:
            return
        self.state.program = self._collect()
        self._push()

    def _push(self) -> None:
        self.state.set_program(self.state.program, origin="blocks")
        self._update_summary()

    def _schedule_push(self) -> None:
        self._push_timer.start()

    def _update_summary(self) -> None:
        total = ast.count_statements(self.state.program)
        if not total:
            self.summary.setText("Блоков пока нет — добавьте первый.")
            return
        points = {p.name: p for p in self.state.preset.points}
        try:
            actions = collect(self.state.program, points, limit=ESTIMATE_LIMIT)
            count = len([a for a in actions if a.__class__.__name__ != "Sleep"])
            if len(actions) >= ESTIMATE_LIMIT:
                self.summary.setText(f"Блоков: {total} · алгоритм бесконечный")
            else:
                self.summary.setText(f"Блоков: {total} · действий за проход: {count}")
        except ScriptError as exc:
            self.summary.setText(f"Блоков: {total} · проверка: {exc}")
        except Exception:  # pragma: no cover - оценка не должна ломать интерфейс
            self.summary.setText(f"Блоков: {total}")

    # ------------------------------------------------------- изменение дерева
    def _insert_target(self) -> tuple[ast.Block, int]:
        """Куда добавить новый блок: внутрь выбранного контейнера или следом."""
        item = self.tree.currentItem()
        if item is None:
            return self.state.program, len(self.state.program)
        if item.data(0, KIND_ROLE) == "group":
            node = item.data(0, NODE_ROLE)
            block = getattr(node, item.data(0, SLOT_ROLE))
            return block, len(block)
        node = item.data(0, NODE_ROLE)
        if ast.is_container(node) and not isinstance(node, ast.If) and item.isExpanded():
            return node.body, len(node.body)
        if isinstance(node, ast.If) and item.isExpanded():
            return node.body, len(node.body)
        found = ast.locate(self.state.program, node.uid)
        if found is None:
            return self.state.program, len(self.state.program)
        block, index = found
        return block, index + 1

    def _default_target(self) -> ast.Target:
        points = self.state.preset.points
        if points:
            return ast.Target(point=points[0].name)
        width, height = self.state.screen_size
        return ast.Target(
            x=ast.Literal(value=float(width // 2), kind="number"),
            y=ast.Literal(value=float(height // 2), kind="number"),
        )

    def _add_block(self, spec: BlockSpec) -> None:
        node = spec.make()
        for attr in ("target", "source"):
            current = getattr(node, attr, None)
            if isinstance(current, ast.Target) and not current.is_point and current.x is None:
                setattr(node, attr, self._default_target())
        block, index = self._insert_target()
        block.insert(index, node)
        self._push()
        self._rebuild_tree(select_uid=node.uid)

    def _duplicate(self) -> None:
        node = self.current_node()
        if node is None:
            return
        found = ast.locate(self.state.program, node.uid)
        if found is None:
            return
        block, index = found
        clone = _clone(node)
        block.insert(index + 1, clone)
        self._push()
        self._rebuild_tree(select_uid=clone.uid)

    def _delete(self) -> None:
        node = self.current_node()
        if node is None:
            return
        found = ast.locate(self.state.program, node.uid)
        if found is None:
            return
        block, index = found
        block.pop(index)
        self._push()
        self._rebuild_tree()

    def _move(self, delta: int) -> None:
        node = self.current_node()
        if node is None:
            return
        found = ast.locate(self.state.program, node.uid)
        if found is None:
            return
        block, index = found
        target = index + delta
        if not (0 <= target < len(block)):
            return
        block[index], block[target] = block[target], block[index]
        self._push()
        self._rebuild_tree(select_uid=node.uid)

    def _outdent(self) -> None:
        """Вынести блок на уровень выше."""
        node = self.current_node()
        if node is None:
            return
        parent = self._find_owner(self.state.program, node.uid)
        if parent is None:
            return
        owner_stmt, block, index = parent
        grand = ast.locate(self.state.program, owner_stmt.uid)
        if grand is None:
            return
        outer_block, outer_index = grand
        block.pop(index)
        outer_block.insert(outer_index + 1, node)
        self._push()
        self._rebuild_tree(select_uid=node.uid)

    def _find_owner(
        self, block: ast.Block, uid: str, owner: Optional[ast.Stmt] = None
    ) -> Optional[tuple[ast.Stmt, ast.Block, int]]:
        """Ищет контейнер, внутри которого лежит инструкция."""
        for index, stmt in enumerate(block):
            if stmt.uid == uid:
                return (owner, block, index) if owner is not None else None
            for _, sub in ast.children_blocks(stmt):
                found = self._find_owner(sub, uid, stmt)
                if found is not None:
                    return found
        return None

    # ----------------------------------------------------------- свойства
    def _clear_form(self) -> None:
        while self.props_form.rowCount():
            self.props_form.removeRow(0)

    def _refresh_points(self) -> None:
        self._show_properties()
        self._update_summary()

    def _show_properties(self) -> None:
        self._clear_form()
        node = self.current_node()
        if node is None:
            self.props_card.setEnabled(False)
            self.props_form.addRow(hint_label("Выберите блок, чтобы настроить его."))
            self.props_host.setMinimumHeight(0)
            return
        self.props_card.setEnabled(True)
        spec = spec_for(node)
        if spec is None:
            return

        title = QLabel(spec.label)
        title.setProperty("role", "title")
        self.props_form.addRow(title)
        if spec.hint:
            self.props_form.addRow(hint_label(spec.hint))

        names = [p.name for p in self.state.preset.points]
        for field in spec.fields:
            widget = self._build_field(node, field, names)
            if widget is not None:
                self.props_form.addRow(field.label, widget)

        note = QLineEdit(node.comment)
        note.setMinimumHeight(30)
        note.setPlaceholderText("примечание к блоку")
        note.textChanged.connect(lambda text, n=node: self._set_comment(n, text))
        self.props_form.addRow("Примечание", note)
        # чтобы область прокрутки не сжимала строки, а показывала полосу прокрутки
        self.props_form.activate()
        self.props_host.setMinimumHeight(self.props_form.minimumSize().height())

    def _build_field(
        self, node: ast.Stmt, field: FieldSpec, point_names: list[str]
    ) -> Optional[QWidget]:
        value = getattr(node, field.key, None)
        editor: QWidget

        if field.kind == "target":
            editor = TargetEditor()
            editor.set_points(point_names)
            editor.set_value(value if isinstance(value, ast.Target) else None)
            editor.changed.connect(
                lambda n=node, f=field, e=editor: self._apply(n, f.key, e.value())
            )
            editor.pickRequested.connect(lambda e=editor: self._request_pick(e))
        elif field.kind == "button":
            editor = ButtonEditor()
            editor.set_value(str(value or "left"))
            editor.currentIndexChanged.connect(
                lambda _=0, n=node, f=field, e=editor: self._apply(n, f.key, e.value())
            )
        elif field.kind == "duration":
            editor = DurationEditor(self.state.config.dialect)
            editor.set_value(value)
            editor.changed.connect(
                lambda n=node, f=field, e=editor: self._apply(n, f.key, e.value())
            )
        elif field.kind == "number":
            editor = NumberEditor(self.state.config.dialect)
            editor.set_value(value)
            editor.changed.connect(
                lambda n=node, f=field, e=editor: self._apply(n, f.key, e.value())
            )
        elif field.kind == "expr":
            editor = ExprEditor(self.state.config.dialect, field.hint)
            editor.set_value(value)
            editor.changed.connect(
                lambda n=node, f=field, e=editor: self._apply(n, f.key, e.value())
            )
        else:  # text | keys | name
            editor = QLineEdit(str(value or ""))
            editor.setPlaceholderText(field.hint)
            editor.textChanged.connect(
                lambda text, n=node, f=field: self._apply(n, f.key, text)
            )

        editor.setMinimumHeight(30)
        if not field.optional:
            return editor

        wrapper = QWidget()
        wrapper.setMinimumHeight(30)
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        box = QCheckBox()
        box.setToolTip(field.hint or "включить параметр")
        box.setChecked(value is not None)
        editor.setEnabled(value is not None)
        box.toggled.connect(
            lambda on, n=node, f=field, e=editor: self._toggle_optional(n, f, e, on)
        )
        layout.addWidget(box)
        layout.addWidget(editor, 1)
        return wrapper

    def _toggle_optional(
        self, node: ast.Stmt, field: FieldSpec, editor: QWidget, enabled: bool
    ) -> None:
        editor.setEnabled(enabled)
        value = editor.value() if enabled and hasattr(editor, "value") else None
        self._apply(node, field.key, value)

    def _apply(self, node: ast.Stmt, key: str, value: Any) -> None:
        if self._loading:
            return
        setattr(node, key, value)
        self._refresh_item_text(node)
        self._schedule_push()

    def _set_comment(self, node: ast.Stmt, text: str) -> None:
        node.comment = text.strip()
        self._refresh_item_text(node)
        self._schedule_push()

    def _refresh_item_text(self, node: ast.Stmt) -> None:
        for item in self._all_items():
            if item.data(0, KIND_ROLE) == "stmt" and item.data(0, NODE_ROLE) is node:
                item.setText(0, self._label(node))
                item.setToolTip(0, node.comment)
                return

    def _request_pick(self, editor: TargetEditor) -> None:
        self.pickRequested.emit(lambda x, y, e=editor: e.set_coords(x, y))


def _clone(stmt: ast.Stmt) -> ast.Stmt:
    """Глубокая копия узла с новыми идентификаторами."""
    import copy

    clone = copy.deepcopy(stmt)
    for node in [clone, *ast.walk([clone])]:
        node.uid = ast.new_uid()
    return clone
