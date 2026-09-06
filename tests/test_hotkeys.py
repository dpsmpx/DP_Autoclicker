"""Горячие клавиши: разбор сочетаний, проверка и регистрация."""

from __future__ import annotations

import pytest

from dp_autoclicker.core.hotkeys import HotkeyManager, describe, normalize, validate


@pytest.mark.parametrize(
    "combo,expected",
    [
        ("f6", "<f6>"),
        ("F6", "<f6>"),
        ("ctrl+shift+s", "<ctrl>+<shift>+s"),
        ("win+d", "<cmd>+d"),
        ("control+alt+delete", "<ctrl>+<alt>+<delete>"),
        ("pageup", "<page_up>"),
        ("escape", "<esc>"),
        ("ctrl + 1", "<ctrl>+1"),
    ],
)
def test_normalize_maps_to_pynput_format(combo, expected):
    assert normalize(combo) == expected


@pytest.mark.parametrize("combo", ["f6", "ctrl+shift+s", "alt+f4", "win+d", "space", "a"])
def test_valid_combos_pass(combo):
    assert validate(combo) == ""


@pytest.mark.parametrize(
    "combo,fragment",
    [
        ("", "не задано"),
        ("ctrl", "обычная клавиша"),
        ("abc", "неизвестная клавиша"),
        ("f99", "неизвестная клавиша"),
        ("ctrl+ctrl+a", "повторяется"),
        ("пробел", "неизвестная клавиша"),
        ("s+ctrl", "не является модификатором"),
    ],
)
def test_invalid_combos_are_explained(combo, fragment):
    problem = validate(combo)
    assert problem and fragment in problem


def test_describe_is_readable():
    assert describe("ctrl+shift+f6") == "Ctrl + Shift + F6"
    assert describe("") == "—"


def test_manager_registers_valid_and_reports_invalid(monkeypatch):
    manager = HotkeyManager()
    calls: list[str] = []
    manager.bind("start_stop", "f6", lambda: calls.append("start"), "старт/стоп")
    manager.bind("pause", "ЧуШь", lambda: calls.append("pause"), "пауза")
    mapping = manager._prepare()

    assert list(mapping) == ["<f6>"]
    assert manager.registered == {"start_stop": "f6"}
    assert any("пауза" in p for p in manager.problems)
    # обработчик корректного сочетания на месте
    mapping["<f6>"]()
    assert calls == ["start"]


def test_manager_detects_conflicting_combos():
    manager = HotkeyManager()
    manager.bind("start_stop", "f6", lambda: None, "старт/стоп")
    manager.bind("panic_stop", "F6", lambda: None, "остановка")
    mapping = manager._prepare()

    assert len(mapping) == 1
    assert "start_stop" in manager.registered and "panic_stop" not in manager.registered
    assert any("занято" in p for p in manager.problems)


def test_one_bad_combo_does_not_break_the_others():
    manager = HotkeyManager()
    manager.bind("start_stop", "f6", lambda: None, "старт/стоп")
    manager.bind("pause", "ctrl+ctrl+z", lambda: None, "пауза")
    manager.bind("panic_stop", "f8", lambda: None, "стоп")
    mapping = manager._prepare()
    assert sorted(mapping) == ["<f6>", "<f8>"]


def test_empty_combo_is_skipped_without_complaint():
    manager = HotkeyManager()
    manager.bind("start_stop", "f6", lambda: None, "старт/стоп")
    manager.bind("pause", "   ", lambda: None, "пауза")
    manager._prepare()
    assert manager.problems == []


def test_start_without_display_reports_reason_and_stays_inactive():
    """В окружении без графики слушатель не запускается, но и не падает."""
    manager = HotkeyManager()
    manager.bind("start_stop", "f6", lambda: None, "старт/стоп")
    started = manager.start()
    if started:  # на машине с графической сессией
        assert manager.active
        assert manager.registered == {"start_stop": "f6"}
        manager.stop()
        assert not manager.active
    else:
        assert not manager.active
        assert manager.error
        assert "недоступны" in manager.status_text()


def test_status_text_lists_problems():
    manager = HotkeyManager()
    manager.bind("pause", "abc", lambda: None, "пауза")
    assert manager.start() is False
    assert "пауза" in manager.status_text()
