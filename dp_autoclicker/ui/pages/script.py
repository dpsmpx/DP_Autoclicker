"""Страница «Скрипт»: тот же алгоритм, только текстом."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...core.script.errors import ScriptError
from ...core.script.parser import parse
from ...core.script.printer import to_source
from ..highlighter import ScriptHighlighter
from ..state import AppState
from ..theme import PALETTE
from ..widgets.common import Card, text_button, tool_button

CHEATSHEET = """
<style>
 code {{ color: {accent}; font-family: Consolas, "DejaVu Sans Mono", monospace; }}
 td {{ padding: 2px 10px 2px 0; }}
 .c {{ color: {muted}; }}
</style>
<table>
<tr><td><code>клик Точка1</code></td><td class="c">нажать в точке</td></tr>
<tr><td><code>клик Точка1 кнопкой пкм раз 3</code></td><td class="c">правой, три раза</td></tr>
<tr><td><code>навести Точка2 за 300мс</code></td><td class="c">плавно подвести курсор</td></tr>
<tr><td><code>перетащить Точка1 к Точка2</code></td><td class="c">перетаскивание</td></tr>
<tr><td><code>прокрутить -3 на Точка1</code></td><td class="c">колесо вниз</td></tr>
<tr><td><code>клавиша ctrl+c</code></td><td class="c">сочетание клавиш</td></tr>
<tr><td><code>печатать "привет"</code></td><td class="c">ввод текста</td></tr>
<tr><td><code>ждать 250мс</code></td><td class="c">пауза</td></tr>
<tr><td><code>ждать 100мс..900мс</code></td><td class="c">случайная пауза</td></tr>
<tr><td><code>повторить 10 раз {{ ... }}</code></td><td class="c">цикл с числом повторов</td></tr>
<tr><td><code>цикл {{ ... }}</code></td><td class="c">до остановки вручную</td></tr>
<tr><td><code>пока x &lt; 5 {{ ... }}</code></td><td class="c">цикл с условием</td></tr>
<tr><td><code>если шанс(30%) {{ ... }} иначе {{ ... }}</code></td><td class="c">ветвление</td></tr>
<tr><td><code>пусть x = итерация * 2</code></td><td class="c">переменная</td></tr>
<tr><td><code>прервать</code> / <code>стоп</code></td><td class="c">выйти из цикла / остановить</td></tr>
<tr><td><code>сообщение "метка"</code></td><td class="c">запись в журнал</td></tr>
<tr><td><code>@(100, 250)</code></td><td class="c">координаты вместо точки</td></tr>
<tr><td><code># текст</code></td><td class="c">комментарий</td></tr>
</table>
<p class="c">Встроенные значения: <code>итерация</code>, <code>время</code>, <code>действий</code>.
Функции: <code>шанс(%)</code>, <code>случайно(a, b)</code>, <code>мин</code>, <code>макс</code>,
<code>округлить</code>, <code>модуль</code>. Английские слова (<code>click</code>, <code>repeat</code>…)
тоже понимаются.</p>
"""


class ScriptPage(QWidget):
    """Текстовый редактор алгоритма с подсветкой и проверкой на лету."""

    #: попросить перейти на строку с ошибкой
    errorChanged = Signal(str)

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        card = Card("Скрипт алгоритма")
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        toolbar.addWidget(
            text_button("Форматировать", "", "wand", self._format), 1
        )
        self.dialect = QComboBox()
        self.dialect.addItem("русский", "ru")
        self.dialect.addItem("english", "en")
        self.dialect.setToolTip("Язык ключевых слов при форматировании")
        self.dialect.setCurrentIndex(0 if state.config.dialect == "ru" else 1)
        self.dialect.currentIndexChanged.connect(self._change_dialect)
        toolbar.addWidget(self.dialect)
        self.help_button = tool_button(
            "list", "Показать шпаргалку по языку", self._toggle_help, checkable=True
        )
        toolbar.addWidget(self.help_button)
        card.body().addLayout(toolbar)

        self.editor = QPlainTextEdit()
        font = QFont("JetBrains Mono", 12)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFixedPitch(True)
        self.editor.setFont(font)
        self.editor.setTabStopDistance(28)
        self.editor.setPlaceholderText(
            "Например:\n\nцикл {\n    клик Точка1\n    ждать 300мс..800мс\n}"
        )
        self.highlighter = ScriptHighlighter(self.editor.document())
        self.editor.textChanged.connect(self._schedule_parse)
        card.add(self.editor)

        self.status = QLabel()
        self.status.setWordWrap(True)
        card.add(self.status)
        root.addWidget(card, 1)

        self.help = QTextBrowser()
        self.help.setHtml(CHEATSHEET.format(accent=PALETTE.accent, muted=PALETTE.muted))
        self.help.setMaximumHeight(230)
        self.help.hide()
        root.addWidget(self.help)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(450)
        self._timer.timeout.connect(self._apply)

        state.programChanged.connect(self._on_program_changed)
        state.presetReplaced.connect(self.reload)
        state.pointsChanged.connect(self._refresh_points)
        self.reload()

    # ------------------------------------------------------------ обновление
    def reload(self) -> None:
        self._set_text(self.state.preset.script)
        self._refresh_points()
        self._validate(self.editor.toPlainText())

    def _on_program_changed(self, origin: str) -> None:
        if origin == "script":
            return
        self._set_text(self.state.preset.script)
        self._validate(self.editor.toPlainText())

    def _set_text(self, text: str) -> None:
        if text == self.editor.toPlainText():
            return
        self._loading = True
        cursor = self.editor.textCursor()
        position = cursor.position()
        self.editor.setPlainText(text)
        cursor.setPosition(min(position, len(text)))
        self.editor.setTextCursor(cursor)
        self._loading = False

    def _refresh_points(self) -> None:
        self.highlighter.set_point_names({p.name for p in self.state.preset.points})

    def _schedule_parse(self) -> None:
        if self._loading:
            return
        self._timer.start()

    # -------------------------------------------------------------- разбор
    def _apply(self) -> None:
        text = self.editor.toPlainText()
        try:
            body = parse(text).body
        except ScriptError as exc:
            self.state.set_script_error(exc, text)
            self._show_error(exc)
            return
        self.state.set_program(body, origin="script", source=text)
        self._validate(text)

    def _validate(self, text: str) -> None:
        try:
            body = parse(text).body
        except ScriptError as exc:
            self._show_error(exc)
            return
        known = {p.name for p in self.state.preset.points}
        from ...core.script.ast_nodes import used_points

        missing = sorted(used_points(body) - known)
        self.editor.setProperty("state", "")
        self.editor.setStyleSheet("")
        if missing:
            self.status.setText(
                "Нет таких точек: " + ", ".join(missing) + " — добавьте их на вкладке «Точки»"
            )
            self.status.setStyleSheet(f"color: {PALETTE.warning};")
            self.errorChanged.emit("points")
            return
        self.status.setText("Синтаксис в порядке")
        self.status.setStyleSheet(f"color: {PALETTE.success};")
        self.errorChanged.emit("")

    def _show_error(self, exc: ScriptError) -> None:
        self.status.setText(str(exc))
        self.status.setStyleSheet(f"color: {PALETTE.danger};")
        self.editor.setStyleSheet(f"border-color: {PALETTE.danger};")
        self.errorChanged.emit(str(exc))

    # ------------------------------------------------------------ действия
    def _format(self) -> None:
        text = self.editor.toPlainText()
        try:
            body = parse(text).body
        except ScriptError as exc:
            self._show_error(exc)
            return
        formatted = to_source(body, self.state.config.dialect)
        self._set_text(formatted)
        self.state.set_program(body, origin="script", source=formatted)
        self._validate(formatted)

    def _change_dialect(self) -> None:
        self.state.config.dialect = str(self.dialect.currentData())
        self._format()

    def _toggle_help(self) -> None:
        self.help.setVisible(self.help_button.isChecked())

    def goto_line(self, line: int) -> None:
        """Ставит курсор на указанную строку (используется журналом)."""
        if line <= 0:
            return
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.movePosition(QTextCursor.MoveOperation.Down, n=line - 1)
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()
