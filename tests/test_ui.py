"""Проверки интерфейса. Работают в режиме offscreen — монитор не нужен."""

from __future__ import annotations

import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402

from dp_autoclicker.app import build_app  # noqa: E402
from dp_autoclicker.core.backends.null import NullBackend  # noqa: E402
from dp_autoclicker.core.engine import ScriptEngine  # noqa: E402
from dp_autoclicker.core.script import ast_nodes as ast  # noqa: E402
from dp_autoclicker.core.script.parser import parse  # noqa: E402
from dp_autoclicker.core.storage import AppConfig, PresetLibrary  # noqa: E402
from dp_autoclicker.ui.blocks_meta import BLOCKS, BY_KEY  # noqa: E402
from dp_autoclicker.ui.pages.blocks import KIND_ROLE, SLOT_ROLE  # noqa: E402
from dp_autoclicker.ui.state import AppState  # noqa: E402


@pytest.fixture(scope="session")
def app():
    return build_app()


@pytest.fixture
def state(app, tmp_path):
    return AppState(
        config=AppConfig(),
        library=PresetLibrary(tmp_path / "presets"),
        screen_size=(1920, 1080),
    )


@pytest.fixture
def window(app, state):
    from dp_autoclicker.ui.main_window import MainWindow

    recorder = NullBackend()
    engine = ScriptEngine(backend_factory=lambda dry, screen: recorder)
    win = MainWindow(state, engine)
    win.recorder = recorder
    win.show()
    app.processEvents()
    yield win
    win.state.mark_dirty(False)
    win.close()


# ------------------------------------------------------------------- окно
def test_window_is_frameless_translucent_and_on_top(window):
    flags = window.windowFlags()
    assert flags & Qt.WindowType.FramelessWindowHint
    assert flags & Qt.WindowType.WindowStaysOnTopHint
    assert window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert 0.35 <= window.windowOpacity() <= 1.0


def test_all_pages_are_reachable(window, app):
    names = []
    for index in range(5):
        window.show_page(index)
        app.processEvents()
        names.append(type(window.stack.currentWidget()).__name__)
    assert names == ["PointsPage", "BlocksPage", "ScriptPage", "SettingsPage", "LogPage"]


def test_compact_mode_hides_pages(window, app):
    window.compact_button.setChecked(True)
    window._toggle_compact()
    app.processEvents()
    assert not window.stack.isVisible()
    window.compact_button.setChecked(False)
    window._toggle_compact()
    app.processEvents()
    assert window.stack.isVisible()


def test_opacity_setting_is_applied(window):
    window.settings_page.opacity.setValue(0.6)
    window.settings_page._apply_window()
    assert window.windowOpacity() == pytest.approx(0.6, abs=0.01)


def test_running_algorithm_updates_log_and_backend(window, app):
    window.state.preset.script = "повторить 2 { клик Точка1\n ждать 10мс\n клик Точка2 }"
    window.state.replace_preset(window.state.preset)
    window.start()
    deadline = time.monotonic() + 5
    while window.engine.is_running and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    window._poll_engine()
    assert len(window.recorder.clicks()) == 4
    assert len(window.log_page._lines) >= 4


# ------------------------------------------------------------------ точки
def test_points_page_add_rename_and_delete(window, app):
    page = window.points_page
    before = len(window.state.preset.points)
    point = page.add_point(640, 480)
    assert len(window.state.preset.points) == before + 1
    assert point.pos == (640, 480)

    page.list.setCurrentRow(0)
    page.name_edit.setText("Кнопка_ОК")
    page._apply_name()
    assert window.state.preset.points[0].name == "Кнопка_ОК"
    # ссылка в алгоритме тоже переименована
    assert "Кнопка_ОК" in window.state.preset.script
    assert "Кнопка_ОК" in ast.used_points(window.state.program)

    page.list.setCurrentRow(0)
    page._delete()
    assert len(window.state.preset.points) == before


def test_points_page_rejects_duplicate_name(window):
    page = window.points_page
    page.add_point(1, 1)
    page.list.setCurrentRow(0)
    existing = window.state.preset.points[1].name
    page.name_edit.setText(existing)
    page._apply_name()
    # страница может быть скрыта в стеке, поэтому проверяем текст, а не видимость
    assert "уже существует" in page.error_label.text()
    assert window.state.preset.points[0].name != existing


# --------------------------------------------------------------- алгоритм
def test_blocks_page_mirrors_the_script(window):
    window.state.preset.script = "цикл {\n    клик Точка1\n    ждать 500мс\n}"
    window.state.replace_preset(window.state.preset)
    labels = [item.text(0) for item in window.blocks_page._all_items()]
    assert labels == ["цикл", "клик Точка1", "ждать 500мс"]


def test_adding_block_updates_script(window):
    page = window.blocks_page
    window.state.preset.script = "клик Точка1"
    window.state.replace_preset(window.state.preset)
    page.tree.setCurrentItem(page._all_items()[0])
    page._add_block(BY_KEY["wait"])
    assert "ждать" in window.state.preset.script
    assert len(window.state.program) == 2


def test_if_block_has_two_branches_and_fills_them(window):
    page = window.blocks_page
    window.state.preset.script = ""
    window.state.replace_preset(window.state.preset)
    page._add_block(BY_KEY["if"])
    groups = [i for i in page._all_items() if i.data(0, KIND_ROLE) == "group"]
    assert [g.data(0, SLOT_ROLE) for g in groups] == ["body", "orelse"]

    page.tree.setCurrentItem(groups[1])  # ветка «иначе»
    page._add_block(BY_KEY["click"])
    node = window.state.program[0]
    assert isinstance(node, ast.If)
    assert len(node.orelse) == 1 and isinstance(node.orelse[0], ast.Click)
    assert "иначе" in window.state.preset.script


def test_new_click_block_uses_first_point(window):
    page = window.blocks_page
    page._add_block(BY_KEY["click"])
    click = page.current_node()
    assert click.target.is_point
    assert click.target.point == window.state.preset.points[0].name


def test_block_delete_duplicate_and_move(window):
    page = window.blocks_page
    window.state.preset.script = "клик Точка1\nждать 100мс"
    window.state.replace_preset(window.state.preset)

    page.tree.setCurrentItem(page._all_items()[0])
    page._duplicate()
    assert len(window.state.program) == 3

    # после дублирования выбрана копия (индекс 1) — сдвигаем её вниз
    page._move(1)
    assert [type(s).__name__ for s in window.state.program] == ["Click", "Wait", "Click"]

    page._delete()
    assert [type(s).__name__ for s in window.state.program] == ["Click", "Wait"]


def test_outdent_moves_block_out_of_container(window):
    page = window.blocks_page
    window.state.preset.script = "цикл {\n    клик Точка1\n}"
    window.state.replace_preset(window.state.preset)
    inner = [i for i in page._all_items() if i.text(0) == "клик Точка1"][0]
    page.tree.setCurrentItem(inner)
    page._outdent()
    assert len(window.state.program) == 2
    assert isinstance(window.state.program[1], ast.Click)


def test_collect_rebuilds_tree_after_drag_and_drop(window):
    """Перетаскивание меняет дерево виджетов — программа собирается заново."""
    page = window.blocks_page
    window.state.preset.script = "цикл {\n    клик Точка1\n}\nждать 100мс"
    window.state.replace_preset(window.state.preset)

    loop_item = page._all_items()[0]
    wait_item = [i for i in page._all_items() if i.text(0) == "ждать 100мс"][0]
    taken = page.tree.invisibleRootItem().takeChild(
        page.tree.invisibleRootItem().indexOfChild(wait_item)
    )
    loop_item.addChild(taken)

    program = page._collect()
    assert len(program) == 1
    assert [type(s).__name__ for s in program[0].body] == ["Click", "Wait"]


def test_property_edit_changes_script(window):
    page = window.blocks_page
    window.state.preset.script = "ждать 500мс"
    window.state.replace_preset(window.state.preset)
    page.tree.setCurrentItem(page._all_items()[0])
    node = page.current_node()

    from dp_autoclicker.core.script.ast_nodes import Literal

    page._apply(node, "duration", Literal(value=1.5, kind="duration"))
    page._push()
    assert "1.5с" in window.state.preset.script


def test_every_block_type_can_be_created_and_printed(window):
    page = window.blocks_page
    window.state.preset.script = ""
    window.state.replace_preset(window.state.preset)
    for spec in BLOCKS:
        page.tree.setCurrentItem(None)
        page._add_block(spec)
    # весь собранный алгоритм должен разбираться обратно
    text = window.state.preset.script
    assert len(parse(text).body) == len(BLOCKS)


# ----------------------------------------------------------------- скрипт
def test_script_page_applies_text_to_blocks(window, app):
    page = window.script_page
    page.editor.setPlainText("повторить 2 {\n    клик Точка1\n}")
    page._apply()
    app.processEvents()
    assert isinstance(window.state.program[0], ast.Repeat)
    assert [i.text(0) for i in window.blocks_page._all_items()] == [
        "повторить 2", "клик Точка1"
    ]


def test_script_page_reports_syntax_error(window, app):
    page = window.script_page
    page.editor.setPlainText("повторить {\n}")
    page._apply()
    app.processEvents()
    assert "Строка" in page.status.text()
    assert window.state.script_error is not None


def test_script_page_warns_about_unknown_points(window, app):
    page = window.script_page
    page.editor.setPlainText("клик НетТакойТочки")
    page._apply()
    app.processEvents()
    assert "НетТакойТочки" in page.status.text()


def test_script_page_formats_and_switches_dialect(window):
    page = window.script_page
    page.editor.setPlainText("повторить 2 {клик Точка1}")
    page._format()
    assert page.editor.toPlainText() == "повторить 2 {\n    клик Точка1\n}"
    page.dialect.setCurrentIndex(1)
    assert page.editor.toPlainText() == "repeat 2 {\n    click Точка1\n}"


# --------------------------------------------------------------- настройки
def test_settings_page_writes_randomization_into_preset(window):
    page = window.settings_page
    page.random_switch.setChecked(True)
    page.jitter.setValue(9)
    page.avoid_switch.setChecked(True)
    page.separation.setValue(4)
    page._apply_random()
    randomization = window.state.preset.randomization
    assert randomization.enabled is True
    assert randomization.position_jitter == 9
    assert randomization.avoid_repeat is True
    assert randomization.min_separation == 4


def test_randomization_controls_are_disabled_when_switch_is_off(window):
    page = window.settings_page
    page.random_switch.setChecked(False)
    page._apply_random()
    assert not page.jitter.isEnabled()
    assert window.state.preset.randomization.enabled is False


def test_settings_page_writes_run_options(window):
    page = window.settings_page
    page.dry_switch.setChecked(True)
    page.speed.setValue(2.0)
    page.max_actions.setValue(500)
    page._apply_run()
    run = window.state.preset.run
    assert run.dry_run is True
    assert run.speed == pytest.approx(2.0)
    assert run.max_actions == 500


# ----------------------------------------------------------------- пресеты
def test_save_and_reopen_preset_through_state(window, tmp_path):
    window.state.preset.name = "Сохранённый"
    window.points_page.add_point(11, 22)
    path = window.state.save_to(tmp_path / "preset.dpclick.json")
    assert path.exists()
    assert window.state.dirty is False

    window._load_path(path)
    assert window.state.preset.name == "Сохранённый"
    assert any(p.pos == (11, 22) for p in window.state.preset.points)


def test_preset_library_dialog_lists_examples(window, app):
    from dp_autoclicker.ui.dialogs import PresetLibraryDialog

    dialog = PresetLibraryDialog(window.state.library)
    dialog._install_examples()
    app.processEvents()
    assert dialog.list.count() >= 3
    dialog.close()


# ------------------------------------------------------------------ прицел
def test_picker_overlay_can_be_created_and_reports_point(app):
    from dp_autoclicker.ui.picker import PickerOverlay, virtual_geometry

    received: list[tuple[int, int]] = []
    overlay = PickerOverlay()
    overlay.picked.connect(lambda x, y: received.append((x, y)))
    overlay.start()
    app.processEvents()
    assert overlay.geometry().size() == virtual_geometry().size()
    overlay._pos.setX(123)
    overlay._pos.setY(456)
    overlay._finish()
    app.processEvents()
    assert received == [(123, 456)]
    overlay.close()


def test_picking_adds_point_to_preset(window, app):
    before = len(window.state.preset.points)
    window._start_point_pick(None)
    window._on_picked(300, 400)
    app.processEvents()
    assert len(window.state.preset.points) == before + 1
    assert window.state.preset.points[-1].pos == (300, 400)
