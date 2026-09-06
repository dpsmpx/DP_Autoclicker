"""Страница «Настройки»: рандомизация, запуск, окно, горячие клавиши."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.backends import probe_backend
from ...core.hotkeys import describe, validate
from ..state import AppState
from ..theme import PALETTE
from ..widgets.common import Card, SliderRow, SwitchRow, expanding, hint_label, text_button

SHAPE_ITEMS = (("circle", "круг"), ("square", "квадрат"), ("gauss", "гаусс (чаще к центру)"))


class SettingsPage(QWidget):
    """Все настройки на одной прокручиваемой странице."""

    #: изменились параметры окна (прозрачность, поверх всех окон, клик-сквозь)
    windowSettingsChanged = Signal()
    #: изменились горячие клавиши
    hotkeysChanged = Signal()

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        root = QVBoxLayout(host)
        root.setContentsMargins(0, 0, 6, 0)
        root.setSpacing(10)
        scroll.setWidget(host)
        outer.addWidget(scroll)

        root.addWidget(self._build_random_card())
        root.addWidget(self._build_run_card())
        root.addWidget(self._build_failsafe_card())
        root.addWidget(self._build_window_card())
        root.addWidget(self._build_hotkeys_card())
        root.addWidget(self._build_about_card())
        root.addStretch(1)

        state.presetReplaced.connect(self.reload)
        state.settingsChanged.connect(self.reload)
        self.reload()

    # -------------------------------------------------------- рандомизация
    def _build_random_card(self) -> Card:
        card = Card("Рандомизация")
        self.random_switch = SwitchRow(
            "Включить рандомизацию",
            "Выключено — программа кликает строго в заданные координаты "
            "и выдерживает точные паузы.",
        )
        self.random_switch.toggled.connect(self._apply_random)
        card.add(self.random_switch)

        self.jitter = SliderRow("Разброс координат", 0, 60, 4, 1, " px")
        self.jitter.valueChanged.connect(self._apply_random)
        card.add(self.jitter)

        shape_row = QHBoxLayout()
        shape_row.addWidget(QLabel("Форма области"))
        self.shape = QComboBox()
        self.shape.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.shape.setMinimumContentsLength(8)
        for value, label in SHAPE_ITEMS:
            self.shape.addItem(label, value)
        self.shape.currentIndexChanged.connect(self._apply_random)
        shape_row.addWidget(self.shape, 1)
        card.body().addLayout(shape_row)

        self.avoid_switch = SwitchRow(
            "Не бить дважды в одно место",
            "Каждое следующее нажатие смещается относительно предыдущего.",
        )
        self.avoid_switch.toggled.connect(self._apply_random)
        card.add(self.avoid_switch)

        self.separation = SliderRow("Минимальный сдвиг", 0, 30, 3, 1, " px")
        self.separation.valueChanged.connect(self._apply_random)
        card.add(self.separation)

        self.delay_jitter = SliderRow("Разброс пауз", 0, 90, 15, 1, " %")
        self.delay_jitter.valueChanged.connect(self._apply_random)
        card.add(self.delay_jitter)

        hold_row = QHBoxLayout()
        hold_row.addWidget(QLabel("Удержание кнопки"))
        self.hold_min = QSpinBox()
        self.hold_max = QSpinBox()
        for spin in (self.hold_min, self.hold_max):
            spin.setMinimumWidth(72)
            spin.setRange(0, 2000)
            spin.setSuffix(" мс")
            spin.valueChanged.connect(self._apply_random)
            hold_row.addWidget(spin, 1)
        card.body().addLayout(hold_row)

        self.humanize_switch = SwitchRow(
            "Плавное движение курсора",
            "Курсор едет по дуге, а не телепортируется.",
        )
        self.humanize_switch.toggled.connect(self._apply_random)
        card.add(self.humanize_switch)

        self.idle = SliderRow("Шанс «отвлечься»", 0, 50, 0, 1, " %")
        self.idle.valueChanged.connect(self._apply_random)
        card.add(self.idle)

        seed_row = QHBoxLayout()
        seed_row.addWidget(QLabel("Зерно случайности"))
        self.seed = QSpinBox()
        self.seed.setRange(0, 999999)
        self.seed.setSpecialValueText("каждый раз новое")
        self.seed.setToolTip(
            "Ненулевое значение делает случайность повторяемой — удобно для отладки."
        )
        self.seed.valueChanged.connect(self._apply_random)
        seed_row.addWidget(self.seed, 1)
        card.body().addLayout(seed_row)

        self._random_widgets = (
            self.jitter, self.shape, self.avoid_switch, self.separation,
            self.delay_jitter, self.hold_min, self.hold_max, self.humanize_switch,
            self.idle, self.seed,
        )
        return card

    # ---------------------------------------------------------------- запуск
    def _build_run_card(self) -> Card:
        card = Card("Запуск")
        self.dry_switch = SwitchRow(
            "Сухой прогон",
            "Ничего не нажимать по-настоящему — только показать действия в журнале.",
        )
        self.dry_switch.toggled.connect(self._apply_run)
        card.add(self.dry_switch)

        self.speed = SliderRow("Скорость", 0.1, 5.0, 1.0, 0.1, "x", decimals=1)
        self.speed.valueChanged.connect(self._apply_run)
        card.add(self.speed)

        self.start_delay = SliderRow("Отсчёт перед стартом", 0, 10, 0, 1, " с")
        self.start_delay.valueChanged.connect(self._apply_run)
        card.add(self.start_delay)

        limit_row = QHBoxLayout()
        limit_row.addWidget(QLabel("Ограничения"))
        self.max_runtime = QSpinBox()
        self.max_runtime.setMinimumWidth(96)
        self.max_runtime.setRange(0, 86400)
        self.max_runtime.setSuffix(" с")
        self.max_runtime.setSpecialValueText("без лимита")
        self.max_runtime.valueChanged.connect(self._apply_run)
        limit_row.addWidget(self.max_runtime, 1)
        self.max_actions = QSpinBox()
        self.max_actions.setMinimumWidth(96)
        self.max_actions.setRange(0, 1000000)
        self.max_actions.setSuffix(" действий")
        self.max_actions.setSpecialValueText("без лимита")
        self.max_actions.valueChanged.connect(self._apply_run)
        limit_row.addWidget(self.max_actions, 1)
        card.body().addLayout(limit_row)
        card.add(hint_label("Ограничения — страховка: алгоритм сам остановится."))
        return card

    # -------------------------------------------------------------- страховка
    def _build_failsafe_card(self) -> Card:
        card = Card("Страховка")
        self.watch_switch = SwitchRow(
            "Пауза, если мышь двигают вручную",
            "Алгоритм запоминает, куда поставил курсор. Если курсор уехал "
            "сам — значит, за мышь взялись вы, и работа приостанавливается.",
        )
        self.watch_switch.toggled.connect(self._apply_failsafe)
        card.add(self.watch_switch)

        self.watch_threshold = SliderRow("Порог срабатывания", 5, 200, 40, 5, " px")
        self.watch_threshold.valueChanged.connect(self._apply_failsafe)
        card.add(self.watch_threshold)

        self.watch_stop_switch = SwitchRow(
            "Останавливать, а не ставить на паузу",
            "Обычно достаточно паузы: продолжить можно кнопкой или "
            "горячей клавишей.",
        )
        self.watch_stop_switch.toggled.connect(self._apply_failsafe)
        card.add(self.watch_stop_switch)
        card.add(
            hint_label(
                "Слежение включается после первого перемещения курсора алгоритмом, "
                "поэтому свободно двигать мышью до старта и в алгоритмах без мыши можно."
            )
        )
        return card

    # ------------------------------------------------------------------ окно
    def _build_window_card(self) -> Card:
        card = Card("Окно")
        self.opacity = SliderRow("Прозрачность окна", 0.35, 1.0, 0.94, 0.01, "", decimals=2)
        self.opacity.valueChanged.connect(self._apply_window)
        card.add(self.opacity)

        self.on_top_switch = SwitchRow("Поверх всех окон", "Окно не прячется за другими.")
        self.on_top_switch.toggled.connect(self._apply_window)
        card.add(self.on_top_switch)

        self.click_through_switch = SwitchRow(
            "Пропускать мышь во время работы",
            "Пока алгоритм выполняется, окно не перехватывает нажатия.",
        )
        self.click_through_switch.toggled.connect(self._apply_window)
        card.add(self.click_through_switch)
        return card

    # ----------------------------------------------------- горячие клавиши
    def _build_hotkeys_card(self) -> Card:
        card = Card("Горячие клавиши")
        self.hotkey_edits: dict[str, QLineEdit] = {}
        labels = {
            "start_stop": "Старт / стоп",
            "pause": "Пауза",
            "panic_stop": "Аварийная остановка",
            "pick_point": "Добавить точку под курсором",
        }
        for key, label in labels.items():
            row = QHBoxLayout()
            title = QLabel(label)
            title.setMinimumWidth(180)
            row.addWidget(title)
            edit = QLineEdit()
            edit.setPlaceholderText("например f6 или ctrl+shift+s")
            edit.textChanged.connect(self._check_hotkey_fields)
            edit.editingFinished.connect(self._apply_hotkeys)
            self.hotkey_edits[key] = edit
            row.addWidget(edit, 1)
            card.body().addLayout(row)

        self.hotkey_status = QLabel()
        self.hotkey_status.setWordWrap(True)
        self.hotkey_status.setProperty("role", "hint")
        card.add(self.hotkey_status)
        card.add_row(
            text_button("Проверить сейчас", "", "check", self._apply_hotkeys),
            expanding(),
        )
        return card

    def _check_hotkey_fields(self) -> None:
        """Подсвечивает поле красным, если сочетание записано неверно."""
        for edit in self.hotkey_edits.values():
            text = edit.text().strip()
            problem = validate(text) if text else ""
            edit.setStyleSheet("" if not problem else f"border-color: {PALETTE.danger};")
            edit.setToolTip(problem or (describe(text) if text else ""))

    def _build_about_card(self) -> Card:
        card = Card("Система")
        available, message = probe_backend()
        status = QLabel(message)
        status.setWordWrap(True)
        status.setStyleSheet(f"color: {PALETTE.success if available else PALETTE.warning};")
        card.add(status)
        if not available:
            card.add(
                hint_label(
                    "Без драйвера ввода доступен только сухой прогон: алгоритм можно "
                    "собрать, проверить и сохранить, но реальных нажатий не будет."
                )
            )
        author_row = QHBoxLayout()
        author_row.addWidget(QLabel("Автор пресетов"))
        self.author = QLineEdit()
        self.author.setPlaceholderText("ваше имя — попадёт в сохранённые пресеты")
        self.author.editingFinished.connect(self._apply_author)
        author_row.addWidget(self.author, 1)
        card.body().addLayout(author_row)
        return card

    # ------------------------------------------------------------ загрузка
    def reload(self) -> None:
        self._loading = True
        try:
            r = self.state.preset.randomization
            self.random_switch.setChecked(r.enabled)
            self.jitter.setValue(r.position_jitter)
            self.shape.setCurrentIndex(max(0, self.shape.findData(r.shape)))
            self.avoid_switch.setChecked(r.avoid_repeat)
            self.separation.setValue(r.min_separation)
            self.delay_jitter.setValue(r.delay_jitter * 100)
            self.hold_min.setValue(int(r.hold_min_ms))
            self.hold_max.setValue(int(r.hold_max_ms))
            self.humanize_switch.setChecked(r.humanize_move)
            self.idle.setValue(r.idle_chance * 100)
            self.seed.setValue(int(r.seed))
            self._update_random_enabled()

            run = self.state.preset.run
            self.dry_switch.setChecked(run.dry_run)
            self.speed.setValue(run.speed)
            self.start_delay.setValue(run.start_delay)
            self.max_runtime.setValue(int(run.max_runtime))
            self.max_actions.setValue(int(run.max_actions))

            failsafe = self.state.config.failsafe
            self.watch_switch.setChecked(failsafe.watch_user_move)
            self.watch_threshold.setValue(failsafe.threshold)
            self.watch_stop_switch.setChecked(failsafe.stop_instead_of_pause)
            self.watch_threshold.setEnabled(failsafe.watch_user_move)
            self.watch_stop_switch.setEnabled(failsafe.watch_user_move)

            window = self.state.config.window
            self.opacity.setValue(window.opacity)
            self.on_top_switch.setChecked(window.always_on_top)
            self.click_through_switch.setChecked(window.click_through_when_running)

            for key, edit in self.hotkey_edits.items():
                edit.setText(getattr(self.state.config.hotkeys, key, ""))
            self._check_hotkey_fields()
            self.author.setText(self.state.config.author)
        finally:
            self._loading = False

    def _update_random_enabled(self) -> None:
        enabled = self.random_switch.isChecked()
        for widget in self._random_widgets:
            widget.setEnabled(enabled)
        self.separation.setEnabled(enabled and self.avoid_switch.isChecked())

    # ------------------------------------------------------------ сохранение
    def _apply_random(self) -> None:
        if self._loading:
            return
        r = self.state.preset.randomization
        r.enabled = self.random_switch.isChecked()
        r.position_jitter = self.jitter.value()
        r.shape = str(self.shape.currentData())
        r.avoid_repeat = self.avoid_switch.isChecked()
        r.min_separation = self.separation.value()
        r.delay_jitter = self.delay_jitter.value() / 100.0
        r.hold_min_ms = float(self.hold_min.value())
        r.hold_max_ms = float(self.hold_max.value())
        r.humanize_move = self.humanize_switch.isChecked()
        r.idle_chance = self.idle.value() / 100.0
        r.seed = self.seed.value()
        self._update_random_enabled()
        self.state.mark_dirty()

    def _apply_run(self) -> None:
        if self._loading:
            return
        run = self.state.preset.run
        run.dry_run = self.dry_switch.isChecked()
        run.speed = self.speed.value()
        run.start_delay = self.start_delay.value()
        run.max_runtime = float(self.max_runtime.value())
        run.max_actions = self.max_actions.value()
        self.state.mark_dirty()

    def _apply_failsafe(self) -> None:
        if self._loading:
            return
        failsafe = self.state.config.failsafe
        failsafe.watch_user_move = self.watch_switch.isChecked()
        failsafe.threshold = self.watch_threshold.value()
        failsafe.stop_instead_of_pause = self.watch_stop_switch.isChecked()
        enabled = failsafe.watch_user_move
        self.watch_threshold.setEnabled(enabled)
        self.watch_stop_switch.setEnabled(enabled)

    def _apply_window(self) -> None:
        if self._loading:
            return
        window = self.state.config.window
        window.opacity = self.opacity.value()
        window.always_on_top = self.on_top_switch.isChecked()
        window.click_through_when_running = self.click_through_switch.isChecked()
        self.windowSettingsChanged.emit()

    def _apply_hotkeys(self) -> None:
        if self._loading:
            return
        for key, edit in self.hotkey_edits.items():
            setattr(self.state.config.hotkeys, key, edit.text().strip().lower())
        self.hotkeysChanged.emit()

    def _apply_author(self) -> None:
        if self._loading:
            return
        self.state.config.author = self.author.text().strip()

    def set_hotkey_status(self, message: str, ok: bool = True) -> None:
        self.hotkey_status.setText(message)
        self.hotkey_status.setStyleSheet(
            f"color: {PALETTE.muted if ok else PALETTE.warning};"
        )
