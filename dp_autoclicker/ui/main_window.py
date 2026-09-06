"""Главное окно: плавающее, полупрозрачное, поверх остальных окон."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizeGrip,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.engine import ScriptEngine
from ..core.hotkeys import HotkeyManager, describe
from ..core.models import PRESET_SUFFIX, Preset, ValidationError
from ..core.runtime.events import EngineEvent
from ..core.templates import blank_preset
from .dialogs import PresetInfoDialog, PresetLibraryDialog
from .icons import icon
from .pages.blocks import BlocksPage
from .pages.log import LogPage
from .pages.points import PointsPage
from .pages.script import ScriptPage
from .pages.settings import SettingsPage
from .picker import PickerOverlay
from .state import AppState
from .theme import PALETTE
from .widgets.common import StatusPill, text_button, tool_button

#: как часто забирать события движка
POLL_MS = 40

NAV_PAGES = (
    ("target", "Точки"),
    ("blocks", "Алгоритм"),
    ("code", "Скрипт"),
    ("gear", "Настройки"),
    ("list", "Журнал"),
)


class MainWindow(QWidget):
    """Компактное окно-панель управления автокликером."""

    #: горячая клавиша нажата; сигнал переносит вызов в поток интерфейса
    hotkeyPressed = Signal(str)

    def __init__(
        self,
        state: AppState,
        engine: Optional[ScriptEngine] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.state = state
        self.engine = engine or ScriptEngine()
        self.hotkeys = HotkeyManager()
        self._drag_offset: Optional[QPoint] = None
        self._pick_callback: Optional[Callable[[int, int], None]] = None
        self._pick_point = None
        #: почему алгоритм на паузе (например, вмешательство пользователя)
        self._pause_reason = ""
        self.hotkeyPressed.connect(self._on_hotkey)

        self.setWindowTitle("DP Autoclicker")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(380, 140)
        self._apply_window_flags()

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        self.shell = QWidget()
        self.shell.setObjectName("Root")
        root.addWidget(self.shell)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 170))
        self.shell.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self.shell)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(10)
        layout.addWidget(self._build_titlebar())
        layout.addWidget(self._build_transport())
        self.nav_bar = self._build_nav()
        layout.addWidget(self.nav_bar)
        layout.addWidget(self._build_pages(), 1)
        layout.addLayout(self._build_footer())

        self.picker = PickerOverlay()
        self.picker.picked.connect(self._on_picked)
        self.picker.cancelled.connect(self._on_pick_cancelled)

        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self._poll_engine)
        self.timer.start()

        state.dirtyChanged.connect(lambda _: self._update_title())
        state.presetReplaced.connect(self._update_title)
        state.pathChanged.connect(lambda _: self._update_title())

        self._restore_geometry()
        self._apply_window_settings()
        self._rebind_hotkeys()
        self._update_title()
        self._update_transport()

    # ---------------------------------------------------------- построение
    def _build_titlebar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(30)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        logo = QLabel()
        logo.setPixmap(icon("target", PALETTE.accent, 18).pixmap(18, 18))
        layout.addWidget(logo)

        self.title_label = QLabel("DP Autoclicker")
        self.title_label.setProperty("role", "title")
        layout.addWidget(self.title_label)
        layout.addStretch(1)

        self.pin_button = tool_button(
            "pin", "Поверх всех окон", self._toggle_on_top, PALETTE.accent, checkable=True
        )
        layout.addWidget(self.pin_button)
        self.compact_button = tool_button(
            "collapse", "Свернуть в компактный режим", self._toggle_compact, checkable=True
        )
        layout.addWidget(self.compact_button)
        layout.addWidget(tool_button("close", "Закрыть", self.close, PALETTE.danger))
        bar.installEventFilter(self)
        self._titlebar = bar
        return bar

    def _build_transport(self) -> QWidget:
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.start_button = text_button("Старт", "primary", "play", self.toggle_run)
        self.start_button.setMinimumHeight(34)
        layout.addWidget(self.start_button, 1)

        self.pause_button = text_button("Пауза", "", "pause", self.toggle_pause)
        self.pause_button.setMinimumHeight(34)
        self.pause_button.setEnabled(False)
        layout.addWidget(self.pause_button)

        self.preset_button = QToolButton()
        self.preset_button.setIcon(icon("save", PALETTE.muted, 18))
        self.preset_button.setIconSize(QSize(18, 18))
        self.preset_button.setToolTip("Пресеты: создать, открыть, сохранить, поделиться")
        self.preset_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.preset_button.setFixedSize(36, 34)
        self.preset_button.setMenu(self._build_preset_menu())
        layout.addWidget(self.preset_button)
        return box

    def _build_preset_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.addAction(icon("plus", PALETTE.muted, 18), "Новый пресет", self.new_preset)
        menu.addAction(icon("open", PALETTE.muted, 18), "Библиотека пресетов…", self.open_library)
        menu.addSeparator()
        menu.addAction(icon("save", PALETTE.muted, 18), "Сохранить", self.save_preset)
        menu.addAction("Сохранить как…", self.save_preset_as)
        menu.addSeparator()
        menu.addAction(icon("import", PALETTE.muted, 18), "Импорт из файла…", self.import_preset)
        menu.addAction(icon("export", PALETTE.muted, 18), "Экспорт в файл…", self.export_preset)
        menu.addSeparator()
        menu.addAction(icon("gear", PALETTE.muted, 18), "Свойства пресета…", self.edit_info)
        return menu

    def _build_nav(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for index, (name, label) in enumerate(NAV_PAGES):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIcon(icon(name, PALETTE.muted, 16))
            button.setIconSize(QSize(16, 16))
            button.setProperty("nav", "1")
            button.clicked.connect(lambda _=False, i=index: self.show_page(i))
            self.nav_group.addButton(button, index)
            layout.addWidget(button, 1)
        return bar

    def _build_pages(self) -> QWidget:
        self.stack = QStackedWidget()
        self.points_page = PointsPage(self.state)
        self.points_page.pickRequested.connect(self._start_point_pick)
        self.blocks_page = BlocksPage(self.state)
        self.blocks_page.pickRequested.connect(self._start_coord_pick)
        self.script_page = ScriptPage(self.state)
        self.settings_page = SettingsPage(self.state)
        self.settings_page.windowSettingsChanged.connect(self._apply_window_settings)
        self.settings_page.hotkeysChanged.connect(self._rebind_hotkeys)
        self.log_page = LogPage()
        for page in (
            self.points_page, self.blocks_page, self.script_page,
            self.settings_page, self.log_page,
        ):
            self.stack.addWidget(page)
        self.show_page(1)
        return self.stack

    def _build_footer(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.status = StatusPill("Готов к запуску")
        layout.addWidget(self.status, 1)
        self.hint_label = QLabel()
        self.hint_label.setProperty("role", "hint")
        layout.addWidget(self.hint_label)
        grip = QSizeGrip(self)
        grip.setFixedSize(14, 14)
        layout.addWidget(grip, 0, Qt.AlignmentFlag.AlignBottom)
        return layout

    # ------------------------------------------------------------ внешний вид
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.shell.geometry())
        painter.setBrush(QColor(PALETTE.bg))
        painter.setPen(QPen(QColor(PALETTE.border), 1))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 16, 16)
        painter.end()

    def _apply_window_flags(self) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self.state.config.window.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def _apply_window_settings(self) -> None:
        window = self.state.config.window
        self.setWindowOpacity(window.opacity)
        was_visible = self.isVisible()
        current_on_top = bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        if current_on_top != window.always_on_top:
            self._apply_window_flags()
            if was_visible:
                self.show()
        self.pin_button.setChecked(window.always_on_top)

    def _toggle_on_top(self) -> None:
        self.state.config.window.always_on_top = self.pin_button.isChecked()
        self._apply_window_settings()

    def _toggle_compact(self) -> None:
        compact = self.compact_button.isChecked()
        self.state.config.window.compact = compact
        self.nav_bar.setVisible(not compact)
        self.stack.setVisible(not compact)
        self.compact_button.setIcon(
            icon("expand" if compact else "collapse", PALETTE.muted, 18)
        )
        self.compact_button.setToolTip(
            "Развернуть окно" if compact else "Свернуть в компактный режим"
        )
        if compact:
            self._expanded_size = self.size()
            self.resize(self.width(), 150)
        else:
            size = getattr(self, "_expanded_size", QSize(460, 620))
            self.resize(size)

    def show_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        button = self.nav_group.button(index)
        if button is not None:
            button.setChecked(True)
        for i, (name, _) in enumerate(NAV_PAGES):
            btn = self.nav_group.button(i)
            if btn is not None:
                btn.setIcon(icon(name, PALETTE.accent if i == index else PALETTE.muted, 16))

    # -------------------------------------------------------- перетаскивание
    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self._titlebar:
            if event.type() == event.Type.MouseButtonPress:
                self._drag_offset = event.globalPosition().toPoint() - self.pos()
                return True
            if event.type() == event.Type.MouseMove and self._drag_offset is not None:
                self.move(event.globalPosition().toPoint() - self._drag_offset)
                return True
            if event.type() == event.Type.MouseButtonRelease:
                self._drag_offset = None
                return True
        return super().eventFilter(watched, event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._titlebar.geometry().contains(self.shell.mapFrom(self, event.pos())):
            self.compact_button.toggle()
            self._toggle_compact()

    # ----------------------------------------------------------- управление
    def toggle_run(self) -> None:
        if self.engine.is_running:
            self.stop()
        else:
            self.start()

    def start(self) -> None:
        if self.engine.is_running:
            return
        if self.state.script_error is not None:
            self._notify(f"Ошибка в алгоритме: {self.state.script_error}", error=True)
            self.show_page(2)
            return
        self.log_page.clear()
        screen = self.state.screen_size
        self._pause_reason = ""
        if self.engine.start(
            self.state.preset,
            self.state.program,
            screen,
            failsafe=self.state.config.failsafe,
        ):
            self._update_transport()
            self._apply_click_through(True)

    def stop(self) -> None:
        self.engine.stop()
        self._apply_click_through(False)
        self._update_transport()

    def toggle_pause(self) -> None:
        if self.engine.is_running:
            self.engine.toggle_pause()
            self._update_transport()

    def _apply_click_through(self, running: bool) -> None:
        """Пока алгоритм работает, окно может не перехватывать мышь."""
        wanted = (
            running
            and self.state.config.window.click_through_when_running
            and self.hotkeys.active
        )
        current = bool(self.windowFlags() & Qt.WindowType.WindowTransparentForInput)
        if wanted == current:
            return
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, wanted)
        self.show()

    def _update_transport(self) -> None:
        running = self.engine.is_running
        paused = self.engine.is_paused
        self.start_button.setText("Стоп" if running else "Старт")
        self.start_button.setIcon(
            icon("stop" if running else "play", "#0B1020", 18)
        )
        self.start_button.setProperty("variant", "danger" if running else "primary")
        self.start_button.style().unpolish(self.start_button)
        self.start_button.style().polish(self.start_button)
        self.pause_button.setEnabled(running)
        self.pause_button.setText("Продолжить" if paused else "Пауза")
        if running:
            if paused:
                text = f"Пауза — {self._pause_reason}" if self._pause_reason else "Пауза"
                self.status.set_state(text, PALETTE.warning)
            else:
                self.status.set_state("Выполняется", PALETTE.success)
        else:
            self.status.set_state("Готов к запуску", PALETTE.faint)

        registered = self.hotkeys.registered
        if self.hotkeys.active and registered:
            parts = [
                f"{describe(registered[action])} — {title}"
                for action, title in (("start_stop", "старт/стоп"), ("panic_stop", "стоп"))
                if action in registered
            ]
            self.hint_label.setText(" · ".join(parts))
            self.hint_label.setToolTip(self.hotkeys.status_text())
        else:
            self.hint_label.setText("горячие клавиши недоступны")
            self.hint_label.setToolTip(self.hotkeys.status_text())

    # ------------------------------------------------------------- события
    def _poll_engine(self) -> None:
        events = self.engine.drain()
        if not events:
            return
        for event in events:
            self._handle_event(event)
        stats = self.engine.stats
        self.log_page.set_counters(stats["actions"], stats["clicks"], stats["keys"])
        self._update_transport()

    def _handle_event(self, event: EngineEvent) -> None:
        self.log_page.append_event(event)
        if event.kind == "paused":
            self._pause_reason = str(event.data.get("reason", ""))
        elif event.kind in ("resumed", "started"):
            self._pause_reason = ""
        if event.kind in ("error", "warning"):
            self._notify(event.message, error=event.kind == "error")
            if event.kind == "error":
                self.show_page(4)
        if event.kind in ("finished", "stopped"):
            self._apply_click_through(False)
        if event.kind == "action":
            self.status.set_state(event.message, PALETTE.success)
        elif event.kind == "countdown":
            self.status.set_state(event.message, PALETTE.warning)

    def _notify(self, message: str, error: bool = False) -> None:
        self.status.set_state(message, PALETTE.danger if error else PALETTE.accent)

    # -------------------------------------------------------------- прицел
    def _start_point_pick(self, point) -> None:
        self._pick_point = point
        self._pick_callback = None
        self._begin_pick()

    def _start_coord_pick(self, callback: Callable[[int, int], None]) -> None:
        self._pick_point = None
        self._pick_callback = callback
        self._begin_pick()

    def _begin_pick(self) -> None:
        self._was_visible = self.isVisible()
        self.hide()
        QTimer.singleShot(120, self.picker.start)

    def _on_picked(self, x: int, y: int) -> None:
        self.show()
        if self._pick_callback is not None:
            self._pick_callback(x, y)
        elif self._pick_point is not None:
            self._pick_point.x, self._pick_point.y = x, y
            self.state.notify_points()
        else:
            self.points_page.add_point(x, y)
            self.show_page(0)
        self._pick_callback = None
        self._pick_point = None

    def _on_pick_cancelled(self) -> None:
        self.show()
        self._pick_callback = None
        self._pick_point = None

    def pick_point_hotkey(self) -> None:
        """Добавляет точку прямо под курсором — без прицела."""
        pos = QGuiApplication.primaryScreen().availableGeometry().center()
        try:
            from PySide6.QtGui import QCursor

            pos = QCursor.pos()
        except Exception:  # pragma: no cover
            pass
        point = self.points_page.add_point(pos.x(), pos.y())
        self._notify(f"Добавлена точка «{point.name}» ({pos.x()}, {pos.y()})")

    # ------------------------------------------------------------- пресеты
    def _update_title(self) -> None:
        mark = " •" if self.state.dirty else ""
        self.title_label.setText(f"{self.state.preset.name}{mark}")
        self.title_label.setToolTip(str(self.state.path or "не сохранён"))

    def _confirm_discard(self) -> bool:
        if not self.state.dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Несохранённые изменения",
            f"Сохранить изменения в «{self.state.preset.name}»?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self.save_preset()
        return True

    def new_preset(self) -> None:
        if not self._confirm_discard():
            return
        preset = blank_preset(*self.state.screen_size)
        preset.author = self.state.config.author
        self.state.replace_preset(preset)
        self._notify("Создан новый пресет")

    def open_library(self) -> None:
        dialog = PresetLibraryDialog(self.state.library, self)
        if dialog.exec() == PresetLibraryDialog.DialogCode.Accepted and dialog.selected:
            self._load_path(dialog.selected)

    def _load_path(self, path: Path) -> None:
        if not self._confirm_discard():
            return
        try:
            preset = Preset.load(path)
        except ValidationError as exc:
            QMessageBox.warning(self, "Не удалось открыть", str(exc))
            return
        width, height = self.state.screen_size
        if preset.needs_rescale(width, height):
            answer = QMessageBox.question(
                self,
                "Другое разрешение экрана",
                f"Пресет собран для экрана {preset.screen.width}×{preset.screen.height}, "
                f"а сейчас {width}×{height}.\nПересчитать координаты точек?",
            )
            if answer == QMessageBox.StandardButton.Yes:
                preset.rescale(width, height)
        self.state.replace_preset(preset, path)
        self._notify(f"Открыт пресет «{preset.name}»")

    def save_preset(self) -> bool:
        if self.state.path is None:
            return self.save_preset_as()
        if not self.state.preset.author:
            self.state.preset.author = self.state.config.author
        try:
            self.state.save_to(self.state.path)
        except OSError as exc:
            QMessageBox.warning(self, "Не удалось сохранить", str(exc))
            return False
        self._notify("Сохранено")
        return True

    def save_preset_as(self) -> bool:
        dialog = PresetInfoDialog(self.state.preset, self)
        if dialog.exec() != PresetInfoDialog.DialogCode.Accepted:
            return False
        dialog.apply()
        if not self.state.preset.author:
            self.state.preset.author = self.state.config.author
        path = self.state.library.path_for(self.state.preset)
        try:
            self.state.save_to(path)
        except OSError as exc:
            QMessageBox.warning(self, "Не удалось сохранить", str(exc))
            return False
        self._notify(f"Сохранено: {path.name}")
        return True

    def edit_info(self) -> None:
        dialog = PresetInfoDialog(self.state.preset, self)
        if dialog.exec() == PresetInfoDialog.DialogCode.Accepted:
            dialog.apply()
            self.state.mark_dirty()
            self._update_title()

    def import_preset(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Импорт пресета", "", f"Пресеты DP (*{PRESET_SUFFIX} *.json)"
        )
        if path:
            self._load_path(Path(path))

    def export_preset(self) -> None:
        suggestion = self.state.library.path_for(self.state.preset).name
        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт пресета", suggestion, f"Пресеты DP (*{PRESET_SUFFIX})"
        )
        if not path:
            return
        try:
            self.state.preset.save(Path(path))
        except OSError as exc:
            QMessageBox.warning(self, "Не удалось экспортировать", str(exc))
            return
        self._notify(f"Экспортировано: {Path(path).name}")

    # ------------------------------------------------------ горячие клавиши
    #: действие -> (подпись, обработчик)
    HOTKEY_ACTIONS = (
        ("start_stop", "старт/стоп"),
        ("pause", "пауза"),
        ("panic_stop", "аварийная остановка"),
        ("pick_point", "новая точка под курсором"),
    )

    def _rebind_hotkeys(self) -> None:
        """Перерегистрирует глобальные сочетания и сообщает о результате."""
        keys = self.state.config.hotkeys
        self.hotkeys.stop()
        self.hotkeys.clear()
        for action, title in self.HOTKEY_ACTIONS:
            self.hotkeys.bind(
                action,
                getattr(keys, action, ""),
                # обработчик выполняется в потоке слушателя pynput,
                # поэтому только отправляем сигнал — Qt поставит его в очередь
                lambda a=action: self.hotkeyPressed.emit(a),
                title,
            )
        ok = self.hotkeys.start()
        if hasattr(self, "settings_page"):
            self.settings_page.set_hotkey_status(self.hotkeys.status_text(), ok)
        self._update_transport()

    def _on_hotkey(self, action: str) -> None:
        """Вызывается уже в потоке интерфейса."""
        combo = getattr(self.state.config.hotkeys, action, "")
        if self.engine.recently_sent(combo):
            # это сочетание только что нажал сам алгоритм — не реагируем
            return
        handlers = {
            "start_stop": self.toggle_run,
            "pause": self.toggle_pause,
            "panic_stop": self.stop,
            "pick_point": self.pick_point_hotkey,
        }
        handler = handlers.get(action)
        if handler is not None:
            handler()

    # ------------------------------------------------------------- закрытие
    def _restore_geometry(self) -> None:
        window = self.state.config.window
        self.resize(window.width, window.height)
        if window.x >= 0 and window.y >= 0:
            self.move(window.x, window.y)
        else:
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                area = screen.availableGeometry()
                self.move(area.right() - window.width - 40, area.top() + 60)
        if window.compact:
            self.compact_button.setChecked(True)
            self._toggle_compact()

    def _store_geometry(self) -> None:
        window = self.state.config.window
        window.x, window.y = self.x(), self.y()
        if not window.compact:
            window.width, window.height = self.width(), self.height()
        window.compact = self.compact_button.isChecked()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.engine.is_running:
            self.engine.stop()
            self.engine.join(2.0)
        if not self._confirm_discard():
            event.ignore()
            return
        self._store_geometry()
        self.state.config.last_preset = str(self.state.path or "")
        try:
            self.state.config.save()
        except OSError:
            pass
        self.hotkeys.stop()
        self.timer.stop()
        self.picker.close()
        event.accept()
