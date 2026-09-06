"""Лексический анализатор DPScript."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import LexError
from .keywords import TIME_UNITS, WORD_TO_CANON

#: односимвольные и двухсимвольные операторы
TWO_CHAR_OPS = ("==", "!=", "<=", ">=", "..", "->")
ONE_CHAR_OPS = "+-*/=<>(){},@%"

IDENT_START = "_"
IDENT_BODY = "_"


def _is_ident_start(ch: str) -> bool:
    return ch.isalpha() or ch in IDENT_START


def _is_ident_body(ch: str) -> bool:
    return ch.isalnum() or ch in IDENT_BODY


@dataclass
class Token:
    #: NUMBER | DURATION | PERCENT | STRING | IDENT | KEYWORD | OP | COMMENT | EOF
    type: str
    value: object
    line: int
    column: int
    #: исходный текст (нужен принтеру и подсветке)
    text: str = ""
    #: комментарий занимает отдельную строку
    own_line: bool = False

    def is_op(self, *ops: str) -> bool:
        return self.type == "OP" and self.value in ops

    def is_kw(self, *words: str) -> bool:
        return self.type == "KEYWORD" and self.value in words

    def __repr__(self) -> str:  # pragma: no cover - отладочное
        return f"Token({self.type}, {self.value!r}, {self.line}:{self.column})"


def tokenize(source: str) -> list[Token]:
    """Разбивает исходный текст на токены."""
    tokens: list[Token] = []
    i = 0
    line = 1
    line_start = 0
    n = len(source)
    line_has_code = False

    while i < n:
        ch = source[i]

        if ch == "\n":
            line += 1
            i += 1
            line_start = i
            line_has_code = False
            continue

        if ch in " \t\r":
            i += 1
            continue

        col = i - line_start + 1

        # комментарий до конца строки
        if ch == "#":
            end = source.find("\n", i)
            end = n if end < 0 else end
            text = source[i + 1 : end].strip()
            tokens.append(
                Token("COMMENT", text, line, col, source[i:end], own_line=not line_has_code)
            )
            i = end
            continue

        # строка в двойных кавычках
        if ch == '"':
            i += 1
            buf: list[str] = []
            while i < n and source[i] != '"':
                if source[i] == "\n":
                    raise LexError("Незакрытая кавычка", line, col)
                if source[i] == "\\" and i + 1 < n:
                    esc = source[i + 1]
                    buf.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(esc, esc))
                    i += 2
                    continue
                buf.append(source[i])
                i += 1
            if i >= n:
                raise LexError("Незакрытая кавычка", line, col)
            i += 1
            tokens.append(Token("STRING", "".join(buf), line, col))
            line_has_code = True
            continue

        # число, возможно с единицей времени или знаком процента
        if ch.isdigit() or (ch == "." and i + 1 < n and source[i + 1].isdigit()):
            start = i
            seen_dot = False
            while i < n and (source[i].isdigit() or (source[i] == "." and not seen_dot)):
                # «..» — это диапазон, а не дробная часть
                if source[i] == ".":
                    if i + 1 < n and source[i + 1] == ".":
                        break
                    seen_dot = True
                i += 1
            number = float(source[start:i])
            # суффикс единицы измерения, приклеенный к числу
            unit_start = i
            while i < n and _is_ident_body(source[i]) and not source[i].isdigit():
                i += 1
            unit = source[unit_start:i].lower()
            if unit:
                if unit not in TIME_UNITS:
                    raise LexError(
                        f"Неизвестная единица измерения «{unit}». Ожидалось мс/с/мин", line, col
                    )
                tokens.append(
                    Token("DURATION", number * TIME_UNITS[unit], line, col, source[start:i])
                )
            elif i < n and source[i] == "%":
                i += 1
                tokens.append(Token("PERCENT", number / 100.0, line, col, source[start:i]))
            else:
                tokens.append(Token("NUMBER", number, line, col, source[start:i]))
            line_has_code = True
            continue

        # идентификатор или ключевое слово
        if _is_ident_start(ch):
            start = i
            while i < n and _is_ident_body(source[i]):
                i += 1
            raw = source[start:i]
            canon = WORD_TO_CANON.get(raw.lower())
            if canon:
                tokens.append(Token("KEYWORD", canon, line, col, raw))
            else:
                tokens.append(Token("IDENT", raw, line, col, raw))
            line_has_code = True
            continue

        # операторы
        two = source[i : i + 2]
        if two in TWO_CHAR_OPS:
            tokens.append(Token("OP", two, line, col, two))
            i += 2
            line_has_code = True
            continue
        if ch in ONE_CHAR_OPS:
            tokens.append(Token("OP", ch, line, col, ch))
            i += 1
            line_has_code = True
            continue

        raise LexError(f"Непонятный символ «{ch}»", line, col)

    tokens.append(Token("EOF", None, line, i - line_start + 1))
    return tokens
