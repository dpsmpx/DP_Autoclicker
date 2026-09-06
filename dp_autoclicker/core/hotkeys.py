"""Глобальные горячие клавиши (работают, когда окно не в фокусе).

Модуль сам по себе ничего не знает об интерфейсе: он проверяет сочетания,
приводит их к формату pynput и запускает слушатель. Обработчики вызываются
из потока слушателя, поэтому в интерфейсе их нужно перекладывать в поток UI
(в главном окне это сделано через сигнал Qt).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

#: клавиши-модификаторы (имена pynput)
MODIFIERS = {"ctrl", "alt", "alt_gr", "shift", "cmd"}

#: именованные клавиши, которые pynput ждёт в угловых скобках
NAMED_KEYS = {
    "enter", "esc", "tab", "space", "backspace", "delete", "insert",
    "home", "end", "page_up", "page_down", "up", "down", "left", "right",
    "caps_lock", "num_lock", "scroll_lock", "print_screen", "pause", "menu",
}

#: как пользователь может написать клавишу -> имя в pynput
ALIASES = {
    "control": "ctrl", "ctl": "ctrl",
    "win": "cmd", "super": "cmd", "meta": "cmd", "command": "cmd",
    "altgr": "alt_gr",
    "return": "enter", "escape": "esc",
    "pageup": "page_up", "pgup": "page_up",
    "pagedown": "page_down", "pgdn": "page_down",
    "capslock": "caps_lock", "numlock": "num_lock",
    "scrolllock": "scroll_lock", "printscreen": "print_screen",
    "del": "delete", "ins": "insert", "spacebar": "space", "esc.": "esc",
}

#: красивые подписи для интерфейса
_TITLES = {
    "ctrl": "Ctrl", "alt": "Alt", "alt_gr": "AltGr", "shift": "Shift", "cmd": "Cmd",
    "enter": "Enter", "esc": "Esc", "tab": "Tab", "space": "Space",
    "backspace": "Backspace", "delete": "Delete", "insert": "Insert",
    "home": "Home", "end": "End", "page_up": "PageUp", "page_down": "PageDown",
    "up": "↑", "down": "↓", "left": "←", "right": "→",
    "caps_lock": "CapsLock", "num_lock": "NumLock", "scroll_lock": "ScrollLock",
    "print_screen": "PrintScreen", "pause": "Pause", "menu": "Menu",
}


def _is_function_key(name: str) -> bool:
    return (
        len(name) >= 2
        and name[0] == "f"
        and name[1:].isdigit()
        and 1 <= int(name[1:]) <= 20
    )


def _parts(combo: str) -> list[str]:
    """Разбирает сочетание на приведённые к каноническому виду части."""
    out: list[str] = []
    for raw in combo.split("+"):
        part = raw.strip().lower()
        if part:
            out.append(ALIASES.get(part, part))
    return out


def validate(combo: str) -> str:
    """Проверяет сочетание. Возвращает текст ошибки или пустую строку."""
    parts = _parts(combo)
    if not parts:
        return "сочетание не задано"
    *modifiers, key = parts
    for modifier in modifiers:
        if modifier not in MODIFIERS:
            return f"«{modifier}» не является модификатором (ctrl, alt, shift, win)"
    if key in MODIFIERS:
        return "нужна обычная клавиша после модификаторов, например ctrl+shift+s"
    if not (len(key) == 1 and key.isalnum()) and key not in NAMED_KEYS and not _is_function_key(key):
        return f"неизвестная клавиша «{key}»"
    if len(set(modifiers)) != len(modifiers):
        return "модификатор повторяется"
    return ""


def normalize(combo: str) -> str:
    """`ctrl+shift+f6` -> `<ctrl>+<shift>+<f6>` (формат pynput)."""
    out: list[str] = []
    for part in _parts(combo):
        if len(part) == 1 and part.isalnum():
            out.append(part)
        else:
            out.append(f"<{part}>")
    return "+".join(out)


def describe(combo: str) -> str:
    """Красивое имя сочетания для интерфейса."""
    parts = _parts(combo)
    if not parts:
        return "—"
    return " + ".join(_TITLES.get(p, p.upper()) for p in parts)


@dataclass
class Binding:
    """Одно сочетание: техническое имя действия, клавиши и обработчик."""

    action: str
    combo: str
    callback: Callable[[], None]
    title: str = ""


class HotkeyManager:
    """Обёртка над pynput.keyboard.GlobalHotKeys.

    Отвечает за три вещи, из-за которых горячие клавиши обычно «не работают»:
    неверно записанное сочетание, конфликт двух действий на одной клавише и
    отсутствие графической сессии. В каждом случае остальные сочетания
    продолжают работать, а причина попадает в `problems` и `error`.
    """

    def __init__(self) -> None:
        self._listener = None
        self._bindings: list[Binding] = []
        #: общая причина, по которой слушатель не запустился
        self.error: str = ""
        #: замечания по отдельным сочетаниям
        self.problems: list[str] = []
        #: сочетания, которые реально зарегистрированы
        self.registered: dict[str, str] = {}

    @property
    def active(self) -> bool:
        return self._listener is not None

    def bind(
        self, action: str, combo: str, callback: Callable[[], None], title: str = ""
    ) -> None:
        self._bindings.append(Binding(action, combo, callback, title or action))

    def clear(self) -> None:
        self._bindings.clear()
        self.problems.clear()
        self.registered.clear()

    # ------------------------------------------------------------- запуск
    def _prepare(self) -> dict[str, Callable[[], None]]:
        """Отбирает корректные сочетания, откладывая проблемные в `problems`."""
        mapping: dict[str, Callable[[], None]] = {}
        taken: dict[str, str] = {}
        self.problems = []
        self.registered = {}
        for binding in self._bindings:
            if not binding.combo.strip():
                continue
            problem = validate(binding.combo)
            if problem:
                self.problems.append(f"{binding.title}: {problem}")
                continue
            key = normalize(binding.combo)
            if key in taken:
                self.problems.append(
                    f"{binding.title}: сочетание {describe(binding.combo)} "
                    f"уже занято действием «{taken[key]}»"
                )
                continue
            taken[key] = binding.title
            mapping[key] = binding.callback
            self.registered[binding.action] = binding.combo
        return mapping

    def start(self) -> bool:
        """Запускает слушатель. False — если ни одно сочетание не работает."""
        self.stop()
        mapping = self._prepare()
        if not mapping:
            self.error = "Не задано ни одного корректного сочетания"
            return False
        try:
            from pynput import keyboard  # type: ignore import

            listener = keyboard.GlobalHotKeys(mapping)
            listener.daemon = True
            listener.start()
        except Exception as exc:
            self._listener = None
            self.registered = {}
            first = str(exc).strip().splitlines()[0] if str(exc).strip() else str(exc)
            self.error = f"{first} Нужна графическая сессия (Windows, macOS или Linux/X11)."
            return False
        self._listener = listener
        self.error = ""
        return True

    def stop(self) -> None:
        listener = self._listener
        self._listener = None
        if listener is not None:
            try:
                listener.stop()
            except Exception:  # pragma: no cover - слушатель уже мёртв
                pass

    def status_text(self) -> str:
        """Понятное описание текущего состояния для интерфейса."""
        if self.active:
            keys = ", ".join(
                f"{describe(b.combo)} — {b.title}"
                for b in self._bindings
                if b.action in self.registered
            )
            text = f"Работают глобально: {keys}"
            if self.problems:
                text += "\nНе назначены: " + "; ".join(self.problems)
            return text
        if self.problems:
            return "Горячие клавиши не работают. " + "; ".join(self.problems)
        return f"Горячие клавиши недоступны: {self.error}" if self.error else ""
