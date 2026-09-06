"""Движок: запуск в потоке, пауза, остановка, события."""

from __future__ import annotations

import time

import pytest

from dp_autoclicker.core.backends.null import NullBackend
from dp_autoclicker.core.engine import ScriptEngine
from dp_autoclicker.core.models import Failsafe, Preset, RunSettings
from dp_autoclicker.core.storage import AppConfig, PresetLibrary


def make(script: str, **run_kwargs) -> tuple[Preset, NullBackend, ScriptEngine]:
    preset = Preset(name="тест", run=RunSettings(**run_kwargs))
    preset.add_point(100, 200, "A")
    preset.add_point(300, 400, "B")
    preset.script = script
    recorder = NullBackend()
    engine = ScriptEngine(backend_factory=lambda dry, screen: recorder)
    return preset, recorder, engine


def wait_for(engine: ScriptEngine, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while engine.is_running and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not engine.is_running, "движок не остановился вовремя"


def kinds(engine: ScriptEngine) -> list[str]:
    return [event.kind for event in engine.drain()]


def test_engine_runs_script_and_reports_finish():
    preset, recorder, engine = make("повторить 3 { клик A ждать 10мс клик B }")
    assert engine.start(preset, screen_size=(1920, 1080))
    wait_for(engine)
    assert len(recorder.clicks()) == 6
    assert recorder.clicks()[0] == (100, 200, "left")
    assert recorder.clicks()[1] == (300, 400, "left")
    assert engine.stats["clicks"] == 6
    events = kinds(engine)
    assert events[0] == "started"
    assert events[-1] == "finished"


def test_engine_refuses_broken_script():
    preset, _, engine = make("повторить {")
    assert engine.start(preset) is False
    assert kinds(engine) == ["error"]


def test_engine_refuses_unknown_points():
    preset, _, engine = make("клик Неизвестная")
    assert engine.start(preset) is False
    events = engine.drain()
    assert events[0].kind == "error"
    assert "Неизвестная" in events[0].message


def test_engine_refuses_empty_script():
    preset, _, engine = make("   ")
    assert engine.start(preset) is False
    assert kinds(engine) == ["warning"]


def test_engine_runs_script_of_comments_only():
    preset, recorder, engine = make("# только комментарий")
    assert engine.start(preset) is True
    wait_for(engine)
    assert recorder.calls == []


def test_engine_can_be_stopped():
    preset, recorder, engine = make("цикл { клик A ждать 20мс }")
    engine.start(preset)
    time.sleep(0.15)
    engine.stop()
    wait_for(engine)
    assert len(recorder.clicks()) >= 1
    assert kinds(engine)[-1] == "stopped"


def test_engine_pause_and_resume():
    preset, recorder, engine = make("цикл { клик A ждать 30мс }")
    engine.start(preset)
    time.sleep(0.1)
    engine.pause()
    assert engine.is_paused
    time.sleep(0.05)
    frozen = len(recorder.clicks())
    time.sleep(0.15)
    assert len(recorder.clicks()) == frozen, "на паузе действий быть не должно"
    engine.resume()
    time.sleep(0.12)
    assert len(recorder.clicks()) > frozen
    engine.stop()
    wait_for(engine)


def test_engine_respects_runtime_limit():
    preset, _, engine = make("цикл { клик A ждать 10мс }", max_runtime=0.2)
    engine.start(preset)
    wait_for(engine, timeout=3.0)
    assert engine.stats["actions"] > 0


def test_engine_reports_runtime_error_with_line():
    preset, _, engine = make("клик A\nждать неизвестная_переменная")
    engine.start(preset)
    wait_for(engine)
    events = engine.drain()
    errors = [e for e in events if e.kind == "error"]
    assert errors and errors[0].line == 2


def test_engine_will_not_start_twice():
    preset, _, engine = make("цикл { клик A ждать 20мс }")
    engine.start(preset)
    assert engine.start(preset) is False
    engine.stop()
    wait_for(engine)


def test_dry_run_uses_null_backend():
    preset = Preset(name="сухой", run=RunSettings(dry_run=True))
    preset.add_point(10, 10, "A")
    preset.script = "клик A"
    engine = ScriptEngine()
    assert engine.start(preset, screen_size=(800, 600))
    wait_for(engine)
    messages = [e.message for e in engine.drain()]
    assert any("сухой прогон" in m for m in messages)


def test_storage_library_roundtrip(tmp_path):
    library = PresetLibrary(tmp_path)
    preset = Preset(name="Мой пресет / v2", description="описание")
    preset.add_point(1, 2, "A")
    path = library.save(preset)
    assert path.exists()
    entries = library.list()
    assert len(entries) == 1 and entries[0].name == "Мой пресет / v2"
    assert library.load(path).points[0].name == "A"
    library.delete(path)
    assert library.list() == []


def test_app_config_roundtrip(tmp_path):
    config = AppConfig(author="Автор")
    config.window.opacity = 0.7
    config.hotkeys.start_stop = "f9"
    config.save(tmp_path / "config.json")
    restored = AppConfig.load(tmp_path / "config.json")
    assert restored.author == "Автор"
    assert restored.window.opacity == pytest.approx(0.7)
    assert restored.hotkeys.start_stop == "f9"


def test_app_config_survives_broken_file(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{сломано", encoding="utf-8")
    assert AppConfig.load(path).dialect == "ru"


# ------------------------------------------- страховка от вмешательства мыши
class Desk(NullBackend):
    """Драйвер с «настоящим» курсором, который может тронуть человек."""

    real = True

    def user_moves_mouse(self, x: int, y: int) -> None:
        self._pos = (int(x), int(y))


def start_watched(
    failsafe: Failsafe, script: str = "цикл { клик A ждать 1с }"
) -> tuple[Desk, ScriptEngine]:
    preset = Preset(name="страховка")
    preset.add_point(100, 200, "A")
    preset.script = script
    desk = Desk()
    engine = ScriptEngine(backend_factory=lambda dry, screen: desk)
    assert engine.start(preset, screen_size=(1920, 1080), failsafe=failsafe)
    return desk, engine


def until(check, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.01)
    return False


def grab_mouse(desk: Desk, distance: int = 300) -> None:
    """Ждём первый клик и «берёмся за мышь», пока алгоритм ждёт."""
    assert until(lambda: len(desk.clicks()) >= 1), "алгоритм не сделал ни одного клика"
    time.sleep(0.1)
    x, y = desk.position()
    desk.user_moves_mouse(x + distance, y + distance)


def test_user_moving_mouse_pauses_the_run():
    desk, engine = start_watched(Failsafe(watch_user_move=True, threshold=40))
    try:
        grab_mouse(desk)
        assert until(lambda: engine.is_paused, 3.0), "движок не встал на паузу"

        events = engine.drain()
        warnings = [e for e in events if e.kind == "warning"]
        paused = [e for e in events if e.kind == "paused"]
        assert warnings and "сдвинут вручную" in warnings[0].message
        assert paused and paused[0].data.get("reason") == "вы двигали мышью"

        frozen = len(desk.clicks())
        time.sleep(0.3)
        assert len(desk.clicks()) == frozen, "на паузе действий быть не должно"
    finally:
        engine.stop()
        wait_for(engine)


def test_run_continues_after_manual_resume():
    desk, engine = start_watched(
        Failsafe(watch_user_move=True, threshold=40), "цикл { клик A ждать 60мс }"
    )
    try:
        grab_mouse(desk)
        assert until(lambda: engine.is_paused, 3.0)
        frozen = len(desk.clicks())
        engine.resume()
        assert until(lambda: len(desk.clicks()) > frozen, 3.0)
        # сразу после продолжения повторной ложной паузы быть не должно
        assert not engine.is_paused
    finally:
        engine.stop()
        wait_for(engine)


def test_failsafe_can_stop_instead_of_pausing():
    desk, engine = start_watched(
        Failsafe(watch_user_move=True, threshold=40, stop_instead_of_pause=True)
    )
    grab_mouse(desk)
    assert until(lambda: not engine.is_running, 3.0), "движок не остановился"


def test_small_drift_below_threshold_is_ignored():
    desk, engine = start_watched(Failsafe(watch_user_move=True, threshold=40))
    try:
        assert until(lambda: len(desk.clicks()) >= 1)
        time.sleep(0.1)
        x, y = desk.position()
        desk.user_moves_mouse(x + 10, y + 10)  # ~14 px
        time.sleep(0.3)
        assert not engine.is_paused
    finally:
        engine.stop()
        wait_for(engine)


def test_failsafe_disabled_lets_the_run_continue():
    desk, engine = start_watched(Failsafe(watch_user_move=False))
    try:
        grab_mouse(desk)
        time.sleep(0.3)
        assert not engine.is_paused
    finally:
        engine.stop()
        wait_for(engine)


def test_normal_run_is_not_interrupted_by_the_failsafe():
    desk, engine = start_watched(
        Failsafe(watch_user_move=True, threshold=40), "повторить 6 { клик A ждать 50мс }"
    )
    wait_for(engine, timeout=6.0)
    assert len(desk.clicks()) == 6
    assert not engine.is_paused


def test_failsafe_defaults_to_watching():
    assert Failsafe().watch_user_move is True
    assert ScriptEngine().failsafe.watch_user_move is True


def test_engine_remembers_keys_it_sent_itself():
    """Скрипт, нажимающий горячую клавишу, не должен сам себя остановить."""
    preset, recorder, engine = make("клавиша f6")
    assert engine.start(preset)
    wait_for(engine)
    assert ("key", "f6") in recorder.calls
    assert engine.recently_sent("f6") is True
    assert engine.recently_sent("F6") is True      # регистр не важен
    assert engine.recently_sent("f8") is False     # другая клавиша — не наша
    assert engine.recently_sent("") is False


def test_sent_key_memory_expires():
    preset, _, engine = make("клавиша f6")
    engine.start(preset)
    wait_for(engine)
    assert engine.recently_sent("f6", window=0.0) is False


def test_fresh_engine_has_not_sent_anything():
    assert ScriptEngine().recently_sent("f6") is False
