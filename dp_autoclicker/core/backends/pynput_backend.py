"""Реальный ввод через библиотеку pynput (Windows, macOS, Linux/X11)."""

from __future__ import annotations

from typing import Any

from .base import BackendError, InputBackend

#: человеческие названия клавиш -> имена в pynput
KEY_ALIASES = {
    "ctrl": "ctrl", "control": "ctrl", "контрол": "ctrl", "стрл": "ctrl",
    "alt": "alt", "альт": "alt",
    "shift": "shift", "шифт": "shift",
    "win": "cmd", "cmd": "cmd", "super": "cmd", "meta": "cmd", "вин": "cmd",
    "enter": "enter", "return": "enter", "ввод": "enter",
    "esc": "esc", "escape": "esc", "эск": "esc",
    "tab": "tab", "таб": "tab",
    "space": "space", "пробел": "space",
    "backspace": "backspace", "back": "backspace",
    "delete": "delete", "del": "delete", "удалить": "delete",
    "insert": "insert", "home": "home", "end": "end",
    "pageup": "page_up", "pagedown": "page_down",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "вверх": "up", "вниз": "down", "влево": "left", "вправо": "right",
}


def _load_pynput() -> Any:
    """Подключает pynput, различая «не установлена» и «нет графической сессии».

    pynput бросает ImportError и в том случае, когда библиотека установлена,
    но подключиться к системе ввода не удалось (например, нет X-сервера),
    поэтому наличие модуля проверяем отдельно.
    """
    try:
        from pynput import keyboard, mouse  # type: ignore import
    except Exception as exc:  # pragma: no cover - зависит от окружения
        import importlib.util

        installed = importlib.util.find_spec("pynput") is not None
        if not installed:
            raise BackendError(
                "Библиотека ввода pynput не установлена. "
                "Выполните «pip install pynput» и перезапустите программу."
            ) from exc
        first_line = str(exc).strip().splitlines()[0] if str(exc).strip() else str(exc)
        raise BackendError(
            f"Управление вводом недоступно в этой сессии: {first_line} "
            "Нужен запуск в графической среде (Windows, macOS или Linux/X11)."
        ) from exc
    return mouse, keyboard


class PynputBackend(InputBackend):
    name = "pynput"
    real = True

    def __init__(self) -> None:
        mouse, keyboard = _load_pynput()
        self._mouse_mod = mouse
        self._keyboard_mod = keyboard
        self._mouse = mouse.Controller()
        self._keyboard = keyboard.Controller()
        self._buttons = {
            "left": mouse.Button.left,
            "right": mouse.Button.right,
            "middle": mouse.Button.middle,
        }

    # ------------------------------------------------------------------ мышь
    def screen_size(self) -> tuple[int, int]:
        try:
            from screeninfo import get_monitors  # type: ignore import

            monitors = get_monitors()
            if monitors:
                width = max(m.x + m.width for m in monitors)
                height = max(m.y + m.height for m in monitors)
                return int(width), int(height)
        except Exception:
            pass
        return (0, 0)

    def position(self) -> tuple[int, int]:
        x, y = self._mouse.position
        return int(x), int(y)

    def move(self, x: int, y: int) -> None:
        self._mouse.position = (int(x), int(y))

    def _button(self, name: str) -> Any:
        try:
            return self._buttons[name]
        except KeyError as exc:
            raise BackendError(f"Неизвестная кнопка мыши: {name}") from exc

    def mouse_down(self, button: str = "left") -> None:
        self._mouse.press(self._button(button))

    def mouse_up(self, button: str = "left") -> None:
        self._mouse.release(self._button(button))

    def scroll(self, dx: int, dy: int) -> None:
        self._mouse.scroll(int(dx), int(dy))

    # -------------------------------------------------------------- клавиши
    def _key(self, name: str) -> Any:
        key_cls = self._keyboard_mod.Key
        alias = KEY_ALIASES.get(name.lower(), name.lower())
        if hasattr(key_cls, alias):
            return getattr(key_cls, alias)
        if len(alias) == 2 and alias[0] == "f" and alias[1].isdigit():
            return getattr(key_cls, alias)
        if alias.startswith("f") and alias[1:].isdigit():
            return getattr(key_cls, alias, None) or alias
        if len(name) == 1:
            return name
        raise BackendError(f"Неизвестная клавиша: «{name}»")

    def key_tap(self, combo: str) -> None:
        parts = [p for p in combo.replace(" ", "").split("+") if p]
        if not parts:
            return
        *modifiers, final = parts
        pressed = [self._key(m) for m in modifiers]
        for key in pressed:
            self._keyboard.press(key)
        try:
            key = self._key(final)
            self._keyboard.press(key)
            self._keyboard.release(key)
        finally:
            for key in reversed(pressed):
                self._keyboard.release(key)

    def type_text(self, text: str) -> None:
        self._keyboard.type(text)
