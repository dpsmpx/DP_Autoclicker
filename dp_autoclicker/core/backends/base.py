"""Абстракция устройства ввода."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BackendError(RuntimeError):
    """Ошибка драйвера ввода."""


class InputBackend(ABC):
    """Минимальный интерфейс, которого достаточно автокликеру."""

    #: человекочитаемое имя для интерфейса
    name = "базовый"
    #: реально ли выполняются действия
    real = False

    @abstractmethod
    def screen_size(self) -> tuple[int, int]:
        ...

    @abstractmethod
    def position(self) -> tuple[int, int]:
        ...

    @abstractmethod
    def move(self, x: int, y: int) -> None:
        ...

    @abstractmethod
    def mouse_down(self, button: str = "left") -> None:
        ...

    @abstractmethod
    def mouse_up(self, button: str = "left") -> None:
        ...

    @abstractmethod
    def scroll(self, dx: int, dy: int) -> None:
        ...

    @abstractmethod
    def key_tap(self, combo: str) -> None:
        ...

    @abstractmethod
    def type_text(self, text: str) -> None:
        ...

    def close(self) -> None:
        """Освободить ресурсы (по умолчанию ничего не нужно)."""
