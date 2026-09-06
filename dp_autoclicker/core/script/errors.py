"""Ошибки разбора и исполнения скрипта."""

from __future__ import annotations


class ScriptError(Exception):
    """Базовая ошибка скрипта с привязкой к позиции в тексте."""

    def __init__(self, message: str, line: int = 0, column: int = 0) -> None:
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column

    def __str__(self) -> str:  # pragma: no cover - тривиально
        if self.line:
            return f"Строка {self.line}: {self.message}"
        return self.message


class LexError(ScriptError):
    """Ошибка на этапе разбора символов."""


class ParseError(ScriptError):
    """Ошибка на этапе разбора грамматики."""


class RuntimeScriptError(ScriptError):
    """Ошибка во время исполнения алгоритма."""
