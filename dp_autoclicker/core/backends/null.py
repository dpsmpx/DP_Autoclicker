"""Бэкенд без реального ввода: журналирует вызовы.

Используется в тестах и в режиме «сухого прогона», когда пользователь хочет
посмотреть, что сделает алгоритм, ничего при этом не нажимая.
"""

from __future__ import annotations

from typing import Any

from .base import InputBackend


class NullBackend(InputBackend):
    name = "сухой прогон"
    real = False

    def __init__(self, screen: tuple[int, int] = (1920, 1080)) -> None:
        self._screen = screen
        self._pos = (screen[0] // 2, screen[1] // 2)
        #: последовательность вызовов вида ("move", x, y)
        self.calls: list[tuple[Any, ...]] = []

    def screen_size(self) -> tuple[int, int]:
        return self._screen

    def position(self) -> tuple[int, int]:
        return self._pos

    def move(self, x: int, y: int) -> None:
        self._pos = (int(x), int(y))
        self.calls.append(("move", int(x), int(y)))

    def mouse_down(self, button: str = "left") -> None:
        self.calls.append(("down", button))

    def mouse_up(self, button: str = "left") -> None:
        self.calls.append(("up", button))

    def scroll(self, dx: int, dy: int) -> None:
        self.calls.append(("scroll", int(dx), int(dy)))

    def key_tap(self, combo: str) -> None:
        self.calls.append(("key", combo))

    def type_text(self, text: str) -> None:
        self.calls.append(("type", text))

    def clicks(self) -> list[tuple[int, int, str]]:
        """Координаты и кнопки всех совершённых нажатий."""
        out: list[tuple[int, int, str]] = []
        pos = (self._screen[0] // 2, self._screen[1] // 2)
        for call in self.calls:
            if call[0] == "move":
                pos = (call[1], call[2])
            elif call[0] == "down":
                out.append((pos[0], pos[1], call[1]))
        return out
