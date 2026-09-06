"""Описание блоков визуального конструктора.

Каждый блок — это узел синтаксического дерева плюс метаданные: как его
показать в списке и какие поля дать в панели свойств.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ..core.script import ast_nodes as ast
from .theme import BLOCK_COLORS


@dataclass(frozen=True)
class FieldSpec:
    """Одно редактируемое поле блока."""

    key: str
    label: str
    #: target | button | duration | number | expr | text | keys | name
    kind: str
    optional: bool = False
    hint: str = ""


@dataclass(frozen=True)
class BlockSpec:
    key: str
    node_type: type
    label: str
    category: str
    color: str
    icon: str
    make: Callable[[], ast.Stmt]
    fields: tuple[FieldSpec, ...] = ()
    hint: str = ""


def _duration(seconds: float) -> ast.Literal:
    return ast.Literal(value=seconds, kind="duration")


def _number(value: float) -> ast.Literal:
    return ast.Literal(value=value, kind="number")


BLOCKS: tuple[BlockSpec, ...] = (
    BlockSpec(
        key="click",
        node_type=ast.Click,
        label="Клик",
        category="Действия",
        color=BLOCK_COLORS["action"],
        icon="target",
        make=lambda: ast.Click(target=ast.Target(point="")),
        fields=(
            FieldSpec("target", "Куда нажать", "target"),
            FieldSpec("button", "Кнопка мыши", "button"),
            FieldSpec("times", "Сколько раз", "number", optional=True, hint="по умолчанию — один"),
            FieldSpec(
                "hold", "Удержание", "duration", optional=True,
                hint="долгое нажатие; по умолчанию берётся из рандомизации",
            ),
        ),
        hint="Нажатие мышью в точку.",
    ),
    BlockSpec(
        key="move",
        node_type=ast.Move,
        label="Навести курсор",
        category="Действия",
        color=BLOCK_COLORS["action"],
        icon="right",
        make=lambda: ast.Move(target=ast.Target(point="")),
        fields=(
            FieldSpec("target", "Куда навести", "target"),
            FieldSpec("duration", "За время", "duration", optional=True),
        ),
    ),
    BlockSpec(
        key="drag",
        node_type=ast.Drag,
        label="Перетащить",
        category="Действия",
        color=BLOCK_COLORS["action"],
        icon="wand",
        make=lambda: ast.Drag(source=ast.Target(point=""), target=ast.Target(point="")),
        fields=(
            FieldSpec("source", "Откуда", "target"),
            FieldSpec("target", "Куда", "target"),
            FieldSpec("duration", "За время", "duration", optional=True),
            FieldSpec("button", "Кнопка мыши", "button"),
        ),
    ),
    BlockSpec(
        key="press",
        node_type=ast.Press,
        label="Зажать кнопку мыши",
        category="Действия",
        color=BLOCK_COLORS["action"],
        icon="down",
        make=lambda: ast.Press(),
        fields=(
            FieldSpec("button", "Кнопка мыши", "button"),
            FieldSpec("target", "В точке", "target", optional=True),
        ),
    ),
    BlockSpec(
        key="release",
        node_type=ast.Release,
        label="Отпустить кнопку мыши",
        category="Действия",
        color=BLOCK_COLORS["action"],
        icon="up",
        make=lambda: ast.Release(),
        fields=(FieldSpec("button", "Кнопка мыши", "button"),),
    ),
    BlockSpec(
        key="scroll",
        node_type=ast.Scroll,
        label="Прокрутка",
        category="Действия",
        color=BLOCK_COLORS["action"],
        icon="list",
        make=lambda: ast.Scroll(amount=_number(3)),
        fields=(
            FieldSpec("amount", "На сколько щелчков", "number", hint="плюс — вверх, минус — вниз"),
            FieldSpec("target", "В точке", "target", optional=True),
        ),
    ),
    BlockSpec(
        key="key",
        node_type=ast.Key,
        label="Клавиши",
        category="Действия",
        color=BLOCK_COLORS["action"],
        icon="code",
        make=lambda: ast.Key(combo="enter"),
        fields=(FieldSpec("combo", "Сочетание", "keys", hint="например ctrl+c или f5"),),
    ),
    BlockSpec(
        key="type",
        node_type=ast.TypeText,
        label="Ввести текст",
        category="Действия",
        color=BLOCK_COLORS["action"],
        icon="code",
        make=lambda: ast.TypeText(text=""),
        fields=(FieldSpec("text", "Текст", "text"),),
    ),
    BlockSpec(
        key="wait",
        node_type=ast.Wait,
        label="Пауза",
        category="Ожидание",
        color=BLOCK_COLORS["wait"],
        icon="pause",
        make=lambda: ast.Wait(duration=_duration(0.5)),
        fields=(
            FieldSpec("duration", "Длительность", "duration", hint="можно задать диапазон"),
        ),
        hint="Ожидание между действиями. Диапазон делает паузу случайной.",
    ),
    BlockSpec(
        key="repeat",
        node_type=ast.Repeat,
        label="Повторить N раз",
        category="Повторы",
        color=BLOCK_COLORS["loop"],
        icon="copy",
        make=lambda: ast.Repeat(count=_number(10)),
        fields=(FieldSpec("count", "Число повторов", "number"),),
    ),
    BlockSpec(
        key="loop",
        node_type=ast.Loop,
        label="Бесконечный цикл",
        category="Повторы",
        color=BLOCK_COLORS["loop"],
        icon="expand",
        make=lambda: ast.Loop(),
        hint="Повторяется, пока вы не остановите алгоритм.",
    ),
    BlockSpec(
        key="while",
        node_type=ast.While,
        label="Пока условие верно",
        category="Повторы",
        color=BLOCK_COLORS["loop"],
        icon="expand",
        make=lambda: ast.While(condition=ast.Binary(op="<", left=ast.Var(name="iteration"), right=_number(10))),
        fields=(FieldSpec("condition", "Условие", "expr"),),
    ),
    BlockSpec(
        key="if",
        node_type=ast.If,
        label="Если …",
        category="Условия",
        color=BLOCK_COLORS["branch"],
        icon="dice",
        make=lambda: ast.If(condition=ast.Call(name="chance", args=[ast.Literal(value=0.5, kind="percent")])),
        fields=(FieldSpec("condition", "Условие", "expr", hint="например: шанс(30%)"),),
        hint="Выполняет вложенные блоки только при выполнении условия.",
    ),
    BlockSpec(
        key="set",
        node_type=ast.SetVar,
        label="Задать переменную",
        category="Прочее",
        color=BLOCK_COLORS["flow"],
        icon="gear",
        make=lambda: ast.SetVar(name="счётчик", value=_number(0)),
        fields=(
            FieldSpec("name", "Имя", "name"),
            FieldSpec("value", "Значение", "expr"),
        ),
    ),
    BlockSpec(
        key="break",
        node_type=ast.Break,
        label="Прервать цикл",
        category="Прочее",
        color=BLOCK_COLORS["flow"],
        icon="minus",
        make=lambda: ast.Break(),
    ),
    BlockSpec(
        key="stop",
        node_type=ast.Stop,
        label="Остановить алгоритм",
        category="Прочее",
        color=BLOCK_COLORS["flow"],
        icon="stop",
        make=lambda: ast.Stop(),
    ),
    BlockSpec(
        key="log",
        node_type=ast.Log,
        label="Сообщение в журнал",
        category="Прочее",
        color=BLOCK_COLORS["flow"],
        icon="list",
        make=lambda: ast.Log(value=ast.Literal(value="метка", kind="string")),
        fields=(FieldSpec("value", "Текст", "expr"),),
    ),
    BlockSpec(
        key="comment",
        node_type=ast.Comment,
        label="Комментарий",
        category="Прочее",
        color=BLOCK_COLORS["note"],
        icon="code",
        make=lambda: ast.Comment(text="заметка"),
        fields=(FieldSpec("text", "Текст", "text"),),
    ),
)

BY_TYPE: dict[type, BlockSpec] = {spec.node_type: spec for spec in BLOCKS}
BY_KEY: dict[str, BlockSpec] = {spec.key: spec for spec in BLOCKS}

CATEGORIES: tuple[str, ...] = ("Действия", "Ожидание", "Повторы", "Условия", "Прочее")


def spec_for(stmt: ast.Stmt) -> Optional[BlockSpec]:
    return BY_TYPE.get(type(stmt))


def by_category() -> dict[str, list[BlockSpec]]:
    grouped: dict[str, list[BlockSpec]] = {name: [] for name in CATEGORIES}
    for spec in BLOCKS:
        grouped.setdefault(spec.category, []).append(spec)
    return grouped
