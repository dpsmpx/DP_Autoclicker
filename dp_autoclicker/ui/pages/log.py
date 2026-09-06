"""Страница «Журнал»: что именно делает алгоритм."""

from __future__ import annotations

import html
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...core.runtime.events import EngineEvent
from ..theme import PALETTE
from ..widgets.common import Card, tool_button

#: цвет строки в зависимости от типа события
COLORS = {
    "started": PALETTE.accent,
    "finished": PALETTE.success,
    "stopped": PALETTE.warning,
    "paused": PALETTE.warning,
    "resumed": PALETTE.accent,
    "countdown": PALETTE.warning,
    "action": PALETTE.muted,
    "log": PALETTE.text,
    "warning": PALETTE.warning,
    "error": PALETTE.danger,
}

MAX_LINES = 600


class LogPage(QWidget):
    """Лента событий движка со счётчиками."""

    #: пользователь дважды кликнул по строке с номером строки скрипта
    lineActivated = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lines: list[str] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        card = Card("Журнал выполнения")
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self.counters = QLabel("Действий: 0 · кликов: 0 · клавиш: 0")
        self.counters.setProperty("role", "muted")
        toolbar.addWidget(self.counters, 1)
        toolbar.addWidget(tool_button("copy", "Скопировать журнал", self._copy))
        toolbar.addWidget(tool_button("trash", "Очистить", self.clear))
        card.body().addLayout(toolbar)

        self.view = QTextBrowser()
        font = QFont("JetBrains Mono", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.view.setFont(font)
        self.view.setOpenExternalLinks(False)
        card.add(self.view)
        root.addWidget(card, 1)
        self.clear()

    # -------------------------------------------------------------- события
    def append_event(self, event: EngineEvent) -> None:
        color = COLORS.get(event.kind, PALETTE.text)
        prefix = f'<span style="color:{PALETTE.faint}">{event.clock}</span> '
        line = event.message
        if event.line:
            line = f"[стр. {event.line}] {line}"
        self._lines.append(
            f'{prefix}<span style="color:{color}">{html.escape(line)}</span>'
        )
        if len(self._lines) > MAX_LINES:
            del self._lines[: len(self._lines) - MAX_LINES]
        self.view.setHtml("<br>".join(self._lines))
        scrollbar = self.view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def set_counters(self, actions: int, clicks: int, keys: int) -> None:
        self.counters.setText(f"Действий: {actions} · кликов: {clicks} · клавиш: {keys}")

    def clear(self) -> None:
        self._lines = []
        self.view.setHtml(
            f'<span style="color:{PALETTE.faint}">Журнал пуст. '
            "Запустите алгоритм — здесь появятся все действия.</span>"
        )
        self.set_counters(0, 0, 0)

    def _copy(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.view.toPlainText())
