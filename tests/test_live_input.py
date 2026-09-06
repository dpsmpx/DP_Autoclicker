"""Проверки с настоящим вводом: реальный курсор и реальные горячие клавиши.

Эти тесты пропускаются в обычном прогоне — им нужен работающий графический
сеанс. Запустить их можно так:

    xvfb-run -a python -m pytest tests/test_live_input.py -q

или просто в своей системе, где есть экран.
"""

from __future__ import annotations

import os
import time

import pytest

from dp_autoclicker.core.backends import probe_backend
from dp_autoclicker.core.engine import ScriptEngine
from dp_autoclicker.core.hotkeys import HotkeyManager
from dp_autoclicker.core.models import Failsafe, Preset

_available, _reason = probe_backend()
pytestmark = pytest.mark.skipif(
    not _available or not (os.environ.get("DISPLAY") or os.name == "nt"),
    reason=f"нужен графический сеанс с настоящим вводом ({_reason})",
)


def until(check, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def clicker():
    """Алгоритм, который щёлкает в углу экрана и ждёт."""
    preset = Preset(name="живая проверка")
    preset.add_point(60, 720, "Угол")
    preset.script = "цикл { клик Угол ждать 300мс }"
    engine = ScriptEngine()
    yield preset, engine
    engine.stop()
    engine.join(3)


def test_real_cursor_move_pauses_the_run(clicker):
    """Пользователь двигает настоящую мышь — алгоритм встаёт на паузу."""
    from pynput.mouse import Controller as Mouse

    preset, engine = clicker
    assert engine.start(
        preset, screen_size=(1280, 800),
        failsafe=Failsafe(watch_user_move=True, threshold=40),
    )
    mouse = Mouse()
    assert until(lambda: mouse.position == (60, 720), 5.0), "алгоритм не увёл курсор в точку"
    time.sleep(0.15)

    x, y = mouse.position
    mouse.position = (x + 350, y - 250)          # «рука пользователя»

    assert until(lambda: engine.is_paused, 4.0), "движение мыши не поставило на паузу"
    reasons = [e.data.get("reason") for e in engine.drain() if e.kind == "paused"]
    assert "вы двигали мышью" in reasons


def test_real_global_hotkey_fires(clicker):
    """Настоящее нажатие F6 доходит до обработчика."""
    from pynput.keyboard import Controller as Keys, Key

    fired: list[str] = []
    manager = HotkeyManager()
    manager.bind("start_stop", "f6", lambda: fired.append("f6"), "старт/стоп")
    manager.bind("panic_stop", "f8", lambda: fired.append("f8"), "стоп")
    assert manager.start(), f"слушатель не запустился: {manager.error}"
    try:
        assert manager.registered == {"start_stop": "f6", "panic_stop": "f8"}
        time.sleep(0.5)
        keyboard = Keys()
        keyboard.press(Key.f6)
        keyboard.release(Key.f6)
        assert until(lambda: "f6" in fired, 3.0), "горячая клавиша не сработала"

        keyboard.press(Key.f8)
        keyboard.release(Key.f8)
        assert until(lambda: "f8" in fired, 3.0)
    finally:
        manager.stop()
    assert not manager.active


def test_invalid_combo_does_not_break_the_working_one(clicker):
    from pynput.keyboard import Controller as Keys, Key

    fired: list[str] = []
    manager = HotkeyManager()
    manager.bind("start_stop", "f6", lambda: fired.append("f6"), "старт/стоп")
    manager.bind("pause", "абракадабра", lambda: fired.append("pause"), "пауза")
    assert manager.start()
    try:
        assert any("пауза" in p for p in manager.problems)
        time.sleep(0.5)
        keyboard = Keys()
        keyboard.press(Key.f6)
        keyboard.release(Key.f6)
        assert until(lambda: "f6" in fired, 3.0), "исправное сочетание перестало работать"
    finally:
        manager.stop()
