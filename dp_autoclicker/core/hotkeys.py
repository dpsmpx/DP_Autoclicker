"""Глобальные горячие клавиши (работают, когда окно не в фокусе)."""

from __future__ import annotations

from typing import Callable

#: имена клавиш, которые pynput ждёт в угловых скобках
_SPECIAL = {
    "ctrl", "control", "alt", "alt_gr", "shift", "cmd", "win", "super",
    "enter", "esc", "escape", "tab", "space", "backspace", "delete", "insert",
    "home", "end", "page_up", "page_down", "up", "down", "left", "right",
    "caps_lock", "num_lock", "scroll_lock", "print_screen", "pause", "menu",
}


def normalize(combo: str) -> str:
    """`ctrl+shift+f6` -> `<ctrl>+<shift>+<f6>` (формат pynput)."""
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    out: list[str] = []
    for part in parts:
        if part in _SPECIAL or (part.startswith("f") and part[1:].isdigit()):
            out.append(f"<{part}>")
        elif len(part) == 1:
            out.append(part)
        else:
            out.append(f"<{part}>")
    return "+".join(out)


def describe(combo: str) -> str:
    """Красивое имя сочетания для интерфейса."""
    names = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "cmd": "Cmd", "esc": "Esc"}
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    return " + ".join(names.get(p, p.upper()) for p in parts)


class HotkeyManager:
    """Тонкая обёртка над pynput.keyboard.GlobalHotKeys.

    Если библиотека или графическая сессия недоступны, менеджер просто
    не запускается — программа продолжает работать с кнопками в окне.
    """

    def __init__(self) -> None:
        self._listener = None
        self._bindings: dict[str, Callable[[], None]] = {}
        self.error: str = ""

    @property
    def active(self) -> bool:
        return self._listener is not None

    def bind(self, combo: str, callback: Callable[[], None]) -> None:
        if combo:
            self._bindings[normalize(combo)] = callback

    def clear(self) -> None:
        self._bindings.clear()

    def start(self) -> bool:
        """Запускает слушатель. Возвращает False и заполняет `error` при сбое."""
        self.stop()
        if not self._bindings:
            return False
        try:
            from pynput import keyboard  # type: ignore import

            self._listener = keyboard.GlobalHotKeys(dict(self._bindings))
            self._listener.daemon = True
            self._listener.start()
            self.error = ""
            return True
        except Exception as exc:
            self._listener = None
            first = str(exc).strip().splitlines()[0] if str(exc).strip() else str(exc)
            self.error = f"Горячие клавиши недоступны: {first}"
            return False

    def stop(self) -> None:
        listener = self._listener
        self._listener = None
        if listener is not None:
            try:
                listener.stop()
            except Exception:  # pragma: no cover
                pass
