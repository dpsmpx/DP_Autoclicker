"""Общее состояние приложения: пресет, разобранный алгоритм, настройки.

Страницы интерфейса не общаются друг с другом напрямую — они читают и
меняют это состояние и слушают его сигналы.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal

from ..core.models import Preset
from ..core.script import ast_nodes as ast
from ..core.script.errors import ScriptError
from ..core.script.parser import parse
from ..core.script.printer import to_source
from ..core.storage import AppConfig, PresetLibrary
from ..core.templates import blank_preset


class AppState(QObject):
    """Единый источник правды для всех страниц."""

    #: пресет заменён целиком (создан, открыт, импортирован)
    presetReplaced = Signal()
    #: изменился список точек
    pointsChanged = Signal()
    #: изменился алгоритм; аргумент — кто его изменил ("blocks" / "script" / "")
    programChanged = Signal(str)
    #: изменились настройки запуска или рандомизации
    settingsChanged = Signal()
    #: появились несохранённые изменения
    dirtyChanged = Signal(bool)
    #: путь текущего файла пресета
    pathChanged = Signal(str)

    def __init__(
        self,
        preset: Optional[Preset] = None,
        config: Optional[AppConfig] = None,
        library: Optional[PresetLibrary] = None,
        screen_size: tuple[int, int] = (1920, 1080),
    ) -> None:
        super().__init__()
        self.config = config or AppConfig()
        self.library = library or PresetLibrary()
        self.screen_size = screen_size
        self._dirty = False
        self.path: Optional[Path] = None
        self.preset = preset or blank_preset(*screen_size)
        self.program: ast.Block = []
        self.script_error: Optional[ScriptError] = None
        self._load_program()

    # ------------------------------------------------------------ алгоритм
    def _load_program(self) -> None:
        try:
            self.program = parse(self.preset.script).body
            self.script_error = None
        except ScriptError as exc:
            self.program = []
            self.script_error = exc

    def set_program(self, body: ast.Block, origin: str = "", source: Optional[str] = None) -> None:
        """Обновляет алгоритм; текст скрипта пересобирается автоматически."""
        self.program = body
        self.script_error = None
        self.preset.script = source if source is not None else to_source(body, self.config.dialect)
        self.mark_dirty()
        self.programChanged.emit(origin)

    def set_script_error(self, error: Optional[ScriptError], text: str) -> None:
        """Текст скрипта не разбирается — сохраняем как есть и помним ошибку."""
        self.script_error = error
        self.preset.script = text
        self.mark_dirty()

    def rendered_script(self) -> str:
        return to_source(self.program, self.config.dialect)

    # -------------------------------------------------------------- точки
    def notify_points(self) -> None:
        self.mark_dirty()
        self.pointsChanged.emit()

    def notify_settings(self) -> None:
        self.mark_dirty()
        self.settingsChanged.emit()

    # ------------------------------------------------------------- пресет
    @property
    def dirty(self) -> bool:
        return self._dirty

    def mark_dirty(self, value: bool = True) -> None:
        if self._dirty != value:
            self._dirty = value
            self.dirtyChanged.emit(value)

    def replace_preset(self, preset: Preset, path: Optional[Path] = None) -> None:
        self.preset = preset
        self.path = Path(path) if path else None
        self._load_program()
        self.mark_dirty(False)
        self.presetReplaced.emit()
        self.pointsChanged.emit()
        self.programChanged.emit("")
        self.settingsChanged.emit()
        self.pathChanged.emit(str(self.path or ""))

    def save_to(self, path: Optional[Path] = None) -> Path:
        target = Path(path) if path else (self.path or self.library.path_for(self.preset))
        if not self.preset.screen.is_known():
            self.preset.screen.width, self.preset.screen.height = self.screen_size
        saved = self.preset.save(target)
        self.path = saved
        self.mark_dirty(False)
        self.pathChanged.emit(str(saved))
        return saved
