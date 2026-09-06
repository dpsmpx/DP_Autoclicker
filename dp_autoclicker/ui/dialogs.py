"""Диалоги: библиотека пресетов и свойства пресета."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..core.models import Preset, ValidationError
from ..core.storage import PresetEntry, PresetLibrary
from ..core.templates import examples
from .widgets.common import hint_label, text_button


class PresetInfoDialog(QDialog):
    """Название, автор, описание и метки пресета."""

    def __init__(self, preset: Preset, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Свойства пресета")
        self.setMinimumWidth(420)
        self.preset = preset

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Название"))
        self.name = QLineEdit(preset.name)
        layout.addWidget(self.name)

        layout.addWidget(QLabel("Автор"))
        self.author = QLineEdit(preset.author)
        self.author.setPlaceholderText("кто собрал пресет")
        layout.addWidget(self.author)

        layout.addWidget(QLabel("Описание"))
        self.description = QPlainTextEdit(preset.description)
        self.description.setPlaceholderText("для чего нужен пресет и как им пользоваться")
        self.description.setMaximumHeight(90)
        layout.addWidget(self.description)

        layout.addWidget(QLabel("Метки (через запятую)"))
        self.tags = QLineEdit(", ".join(preset.tags))
        layout.addWidget(self.tags)

        layout.addWidget(
            hint_label(
                "Пресет сохраняется вместе с точками, алгоритмом и настройками "
                "рандомизации — им можно поделиться одним файлом."
            )
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply(self) -> None:
        self.preset.name = self.name.text().strip() or "Пресет"
        self.preset.author = self.author.text().strip()
        self.preset.description = self.description.toPlainText().strip()
        self.preset.tags = [t.strip() for t in self.tags.text().split(",") if t.strip()]


class PresetLibraryDialog(QDialog):
    """Список сохранённых пресетов с импортом, экспортом и примерами."""

    def __init__(self, library: PresetLibrary, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Библиотека пресетов")
        self.setMinimumSize(520, 420)
        self.library = library
        self.selected: Optional[Path] = None

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _: self._open())
        self.list.currentRowChanged.connect(self._update_details)
        layout.addWidget(self.list, 1)

        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setProperty("role", "hint")
        self.details.setMinimumHeight(52)
        layout.addWidget(self.details)

        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(text_button("Открыть", "primary", "open", self._open))
        row.addWidget(text_button("Удалить", "danger", "trash", self._delete))
        row.addWidget(text_button("Добавить примеры", "", "wand", self._install_examples))
        row.addStretch(1)
        row.addWidget(text_button("Закрыть", "ghost", "", self.reject))
        layout.addLayout(row)

        self.entries: list[PresetEntry] = []
        self.refresh()

    def refresh(self) -> None:
        self.entries = self.library.list()
        self.list.clear()
        for entry in self.entries:
            item = QListWidgetItem(f"{entry.name}   ·   точек: {entry.points}")
            item.setToolTip(entry.description or "без описания")
            self.list.addItem(item)
        if self.entries:
            self.list.setCurrentRow(0)
        else:
            self.details.setText(
                "Пресетов пока нет. Нажмите «Добавить примеры», чтобы посмотреть, "
                "как устроены готовые алгоритмы."
            )

    def _current(self) -> Optional[PresetEntry]:
        row = self.list.currentRow()
        if 0 <= row < len(self.entries):
            return self.entries[row]
        return None

    def _update_details(self) -> None:
        entry = self._current()
        if entry is None:
            self.details.setText("")
            return
        parts = [entry.description or "без описания"]
        if entry.author:
            parts.append(f"автор: {entry.author}")
        parts.append(entry.path.name)
        self.details.setText("\n".join(parts))

    def _open(self) -> None:
        entry = self._current()
        if entry is None:
            return
        self.selected = entry.path
        self.accept()

    def _delete(self) -> None:
        entry = self._current()
        if entry is None:
            return
        answer = QMessageBox.question(
            self, "Удалить пресет", f"Удалить «{entry.name}» без возможности отмены?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.library.delete(entry.path)
        except ValidationError as exc:
            QMessageBox.warning(self, "Не получилось", str(exc))
        self.refresh()

    def _install_examples(self) -> None:
        width, height = 1920, 1080
        screen = self.screen()
        if screen is not None:
            width, height = screen.geometry().width(), screen.geometry().height()
        for preset in examples(width, height):
            path = self.library.path_for(preset)
            if not path.exists():
                self.library.save(preset)
        self.refresh()
