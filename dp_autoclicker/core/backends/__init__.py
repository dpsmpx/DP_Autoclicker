"""Выбор драйвера ввода."""

from __future__ import annotations

from .base import BackendError, InputBackend
from .null import NullBackend

__all__ = ["InputBackend", "BackendError", "NullBackend", "create_backend", "probe_backend"]


def create_backend(dry_run: bool = False, screen: tuple[int, int] = (1920, 1080)) -> InputBackend:
    """Создаёт драйвер ввода; при сухом прогоне — заглушку."""
    if dry_run:
        return NullBackend(screen)
    from .pynput_backend import PynputBackend

    return PynputBackend()


def probe_backend() -> tuple[bool, str]:
    """Проверяет, доступен ли реальный ввод. Возвращает (доступен, описание)."""
    try:
        from .pynput_backend import PynputBackend

        backend = PynputBackend()
        backend.position()
        return True, f"Драйвер ввода: {backend.name}"
    except Exception as exc:
        return False, f"Реальный ввод недоступен: {exc}"
