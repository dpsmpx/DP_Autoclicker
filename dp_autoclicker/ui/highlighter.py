"""Подсветка синтаксиса DPScript."""

from __future__ import annotations

import re
from typing import Optional

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextDocument

from ..core.script.keywords import FUNC_TO_CANON, STATEMENT_KEYWORDS, VAR_TO_CANON, WORD_TO_CANON
from .theme import PALETTE


def _format(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(color))
    if bold:
        fmt.setFontWeight(QFont.Weight.DemiBold)
    fmt.setFontItalic(italic)
    return fmt


class ScriptHighlighter(QSyntaxHighlighter):
    """Раскрашивает команды, значения, строки и комментарии."""

    def __init__(self, document: Optional[QTextDocument] = None) -> None:
        super().__init__(document)
        self.point_names: set[str] = set()

        commands = sorted(
            (w for w, canon in WORD_TO_CANON.items() if canon in STATEMENT_KEYWORDS),
            key=len,
            reverse=True,
        )
        modifiers = sorted(
            (w for w, canon in WORD_TO_CANON.items() if canon not in STATEMENT_KEYWORDS),
            key=len,
            reverse=True,
        )
        self.rules: list[tuple[QRegularExpression, QTextCharFormat]] = [
            (self._words(commands), _format(PALETTE.accent, bold=True)),
            (self._words(modifiers), _format(PALETTE.purple)),
            (self._words(sorted(FUNC_TO_CANON, key=len, reverse=True)), _format(PALETTE.success)),
            (self._words(sorted(VAR_TO_CANON, key=len, reverse=True)), _format(PALETTE.warning)),
            (
                QRegularExpression(r"\b\d+(?:\.\d+)?(?:мс|сек|мин|ms|sec|min|[смs])?%?"),
                _format(PALETTE.warning),
            ),
            (QRegularExpression(r"@\s*\("), _format(PALETTE.danger)),
            (QRegularExpression(r'"[^"\\]*(?:\\.[^"\\]*)*"'), _format("#9FD356")),
        ]
        self.comment_format = _format(PALETTE.faint, italic=True)
        self.point_format = _format(PALETTE.text, bold=True)
        self.unknown_point_format = _format(PALETTE.danger)
        self.ident_re = QRegularExpression(r"[A-Za-zЀ-ӿ_][A-Za-z0-9Ѐ-ӿ_]*")

    @staticmethod
    def _words(words: list[str]) -> QRegularExpression:
        pattern = r"(?<![A-Za-z0-9_Ѐ-ӿ])(?:" + "|".join(re.escape(w) for w in words) + r")(?![A-Za-z0-9_Ѐ-ӿ])"
        expr = QRegularExpression(pattern)
        expr.setPatternOptions(QRegularExpression.PatternOption.CaseInsensitiveOption)
        return expr

    def set_point_names(self, names: set[str]) -> None:
        self.point_names = set(names)
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt API
        # имена точек: известные — светлым, неизвестные — красным
        it = self.ident_re.globalMatch(text)
        while it.hasNext():
            match = it.next()
            word = match.captured(0)
            if word.lower() in WORD_TO_CANON or word.lower() in FUNC_TO_CANON:
                continue
            if word.lower() in VAR_TO_CANON:
                continue
            fmt = self.point_format if word in self.point_names else self.unknown_point_format
            self.setFormat(match.capturedStart(), match.capturedLength(), fmt)

        for expr, fmt in self.rules:
            it = expr.globalMatch(text)
            while it.hasNext():
                match = it.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)

        hash_index = text.find("#")
        if hash_index >= 0:
            quote = text.find('"')
            if quote < 0 or quote > hash_index:
                self.setFormat(hash_index, len(text) - hash_index, self.comment_format)
