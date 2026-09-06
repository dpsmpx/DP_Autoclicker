"""Элементарные действия, которые интерпретатор передаёт движку."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Action:
    """Базовое действие. `uid`/`line` указывают на инструкцию-источник."""

    uid: str = ""
    line: int = 0

    @property
    def title(self) -> str:  # pragma: no cover - переопределяется
        return type(self).__name__


@dataclass
class MoveTo(Action):
    x: int = 0
    y: int = 0
    duration: float = 0.0
    #: промежуточные точки для «человечного» движения
    path: list[tuple[int, int]] = field(default_factory=list)

    @property
    def title(self) -> str:
        return f"курсор → ({self.x}, {self.y})"


@dataclass
class ClickAt(Action):
    x: int = 0
    y: int = 0
    button: str = "left"
    hold: float = 0.0
    duration: float = 0.0
    path: list[tuple[int, int]] = field(default_factory=list)

    @property
    def title(self) -> str:
        names = {"left": "ЛКМ", "right": "ПКМ", "middle": "СКМ"}
        return f"клик {names.get(self.button, self.button)} ({self.x}, {self.y})"


@dataclass
class MouseDown(Action):
    x: Optional[int] = None
    y: Optional[int] = None
    button: str = "left"

    @property
    def title(self) -> str:
        return f"зажать {self.button}"


@dataclass
class MouseUp(Action):
    button: str = "left"

    @property
    def title(self) -> str:
        return f"отпустить {self.button}"


@dataclass
class ScrollBy(Action):
    dx: int = 0
    dy: int = 0

    @property
    def title(self) -> str:
        return f"прокрутка {self.dy:+d}"


@dataclass
class KeyTap(Action):
    combo: str = ""

    @property
    def title(self) -> str:
        return f"клавиши {self.combo}"


@dataclass
class TypeText(Action):
    text: str = ""

    @property
    def title(self) -> str:
        short = self.text if len(self.text) <= 24 else self.text[:21] + "…"
        return f"ввод «{short}»"


@dataclass
class Sleep(Action):
    seconds: float = 0.0

    @property
    def title(self) -> str:
        return f"пауза {self.seconds * 1000:.0f} мс"


@dataclass
class LogMessage(Action):
    message: str = ""

    @property
    def title(self) -> str:
        return self.message
