"""Узлы синтаксического дерева DPScript.

Дерево — единственный источник правды: и текстовый редактор, и визуальный
конструктор блоков читают и пишут именно его.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

Block = list["Stmt"]


def _uid() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Node:
    """Базовый узел: уникальный id (для подсветки в UI) и строка в исходнике."""

    line: int = 0
    uid: str = field(default_factory=_uid, compare=False)


# --------------------------------------------------------------- выражения
@dataclass
class Expr(Node):
    pass


@dataclass
class Literal(Expr):
    """Число, длительность (в секундах), доля процента, строка или логическое."""

    value: Any = 0
    #: number | duration | percent | string | bool
    kind: str = "number"


@dataclass
class Var(Expr):
    name: str = ""


@dataclass
class Range(Expr):
    """Диапазон `a..b`: при исполнении превращается в случайное значение."""

    low: Optional[Expr] = None
    high: Optional[Expr] = None


@dataclass
class Unary(Expr):
    op: str = "-"
    operand: Optional[Expr] = None


@dataclass
class Binary(Expr):
    op: str = "+"
    left: Optional[Expr] = None
    right: Optional[Expr] = None


@dataclass
class Call(Expr):
    name: str = ""
    args: list[Expr] = field(default_factory=list)


@dataclass
class Target(Node):
    """Цель действия: имя точки либо явные координаты `@(x, y)`."""

    point: str = ""
    x: Optional[Expr] = None
    y: Optional[Expr] = None

    @property
    def is_point(self) -> bool:
        return bool(self.point)


# --------------------------------------------------------------- инструкции
@dataclass
class Stmt(Node):
    """Базовая инструкция. `comment` — примечание в конце строки."""

    comment: str = ""


@dataclass
class Click(Stmt):
    target: Optional[Target] = None
    button: str = "left"
    times: Optional[Expr] = None
    hold: Optional[Expr] = None


@dataclass
class Move(Stmt):
    target: Optional[Target] = None
    duration: Optional[Expr] = None


@dataclass
class Drag(Stmt):
    source: Optional[Target] = None
    target: Optional[Target] = None
    duration: Optional[Expr] = None
    button: str = "left"


@dataclass
class Press(Stmt):
    button: str = "left"
    target: Optional[Target] = None


@dataclass
class Release(Stmt):
    button: str = "left"


@dataclass
class Scroll(Stmt):
    amount: Optional[Expr] = None
    target: Optional[Target] = None


@dataclass
class Key(Stmt):
    combo: str = ""


@dataclass
class TypeText(Stmt):
    text: str = ""


@dataclass
class Wait(Stmt):
    duration: Optional[Expr] = None


@dataclass
class Repeat(Stmt):
    count: Optional[Expr] = None
    body: Block = field(default_factory=list)


@dataclass
class Loop(Stmt):
    body: Block = field(default_factory=list)


@dataclass
class While(Stmt):
    condition: Optional[Expr] = None
    body: Block = field(default_factory=list)


@dataclass
class If(Stmt):
    condition: Optional[Expr] = None
    body: Block = field(default_factory=list)
    orelse: Block = field(default_factory=list)


@dataclass
class SetVar(Stmt):
    name: str = ""
    value: Optional[Expr] = None


@dataclass
class Break(Stmt):
    pass


@dataclass
class Stop(Stmt):
    pass


@dataclass
class Log(Stmt):
    value: Optional[Expr] = None


@dataclass
class Comment(Stmt):
    """Комментарий на отдельной строке — сохраняется при round-trip."""

    text: str = ""


@dataclass
class Program(Node):
    body: Block = field(default_factory=list)


#: инструкции, у которых есть вложенные блоки
CONTAINERS: dict[type, tuple[str, ...]] = {
    Repeat: ("body",),
    Loop: ("body",),
    While: ("body",),
    If: ("body", "orelse"),
}


def children_blocks(stmt: Stmt) -> list[tuple[str, Block]]:
    """Возвращает пары (имя поля, блок) для контейнерных инструкций."""
    return [(name, getattr(stmt, name)) for name in CONTAINERS.get(type(stmt), ())]


def walk(block: Block):
    """Обходит дерево инструкций сверху вниз."""
    for stmt in block:
        yield stmt
        for _, sub in children_blocks(stmt):
            yield from walk(sub)


def find_by_uid(block: Block, uid: str) -> Optional[Stmt]:
    for stmt in walk(block):
        if stmt.uid == uid:
            return stmt
    return None


def used_points(block: Block) -> set[str]:
    """Имена точек, на которые ссылается алгоритм."""
    names: set[str] = set()
    for stmt in walk(block):
        for attr in ("target", "source"):
            target = getattr(stmt, attr, None)
            if isinstance(target, Target) and target.is_point:
                names.add(target.point)
    return names


def count_statements(block: Block) -> int:
    return sum(1 for stmt in walk(block) if not isinstance(stmt, Comment))


def rename_point(block: Block, old: str, new: str) -> int:
    """Переименовывает точку во всех ссылках дерева. Возвращает число замен."""
    count = 0
    for stmt in walk(block):
        for attr in ("target", "source"):
            target = getattr(stmt, attr, None)
            if isinstance(target, Target) and target.point == old:
                target.point = new
                count += 1
    return count


def new_uid() -> str:
    """Новый идентификатор узла (нужен при копировании блоков)."""
    return _uid()


def locate(block: Block, uid: str) -> Optional[tuple[Block, int]]:
    """Находит инструкцию по uid и возвращает (список-владелец, индекс)."""
    for index, stmt in enumerate(block):
        if stmt.uid == uid:
            return block, index
        for _, sub in children_blocks(stmt):
            found = locate(sub, uid)
            if found is not None:
                return found
    return None


def is_container(stmt: Stmt) -> bool:
    return type(stmt) in CONTAINERS
