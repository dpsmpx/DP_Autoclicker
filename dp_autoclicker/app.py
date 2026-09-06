"""Точка входа: запуск графического интерфейса и самопроверка."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

from .core.models import Preset, ValidationError
from .core.storage import AppConfig, PresetLibrary

APP_NAME = "DP Autoclicker"
VERSION = "1.0.0"


def _screen_size(app) -> tuple[int, int]:
    from PySide6.QtGui import QGuiApplication

    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return (1920, 1080)
    geometry = screen.geometry()
    return (geometry.width(), geometry.height())


def build_app(argv: Optional[list[str]] = None):
    """Создаёт QApplication с общей темой."""
    from PySide6.QtWidgets import QApplication

    from .ui.theme import stylesheet

    app = QApplication.instance() or QApplication(argv or sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)
    app.setStyleSheet(stylesheet())
    return app


def build_window(app, preset_path: Optional[Path] = None):
    """Собирает главное окно вместе с состоянием и движком."""
    from .core.engine import ScriptEngine
    from .ui.main_window import MainWindow
    from .ui.state import AppState

    config = AppConfig.load()
    library = PresetLibrary()
    size = _screen_size(app)

    preset = None
    path = preset_path
    if path is None and config.last_preset:
        candidate = Path(config.last_preset)
        if candidate.exists():
            path = candidate
    if path is not None:
        try:
            preset = Preset.load(path)
        except ValidationError:
            preset, path = None, None

    state = AppState(preset=preset, config=config, library=library, screen_size=size)
    if path is not None:
        state.path = path
        state.mark_dirty(False)
    return MainWindow(state, ScriptEngine())


def run_gui(preset_path: Optional[Path] = None) -> int:
    app = build_app()
    window = build_window(app, preset_path)
    window.show()
    return app.exec()


def self_check(verbose: bool = True) -> int:
    """Быстрая проверка работоспособности без графического режима."""
    from .core.backends.null import NullBackend
    from .core.engine import ScriptEngine
    from .core.runtime.interpreter import collect
    from .core.script.parser import parse
    from .core.script.printer import to_source
    from .core.templates import examples

    problems: list[str] = []

    def say(text: str) -> None:
        if verbose:
            print(text)

    say(f"{APP_NAME} {VERSION} — самопроверка")

    for preset in examples():
        title = preset.name
        try:
            body = parse(preset.script).body
        except Exception as exc:
            problems.append(f"«{title}»: скрипт не разбирается — {exc}")
            continue
        try:
            restored = to_source(body)
            if to_source(parse(restored).body) != restored:
                problems.append(f"«{title}»: текст не совпадает после пересборки")
        except Exception as exc:
            problems.append(f"«{title}»: ошибка печати — {exc}")
        try:
            points = {p.name: p for p in preset.points}
            actions = collect(body, points, limit=200)
            say(f"  ✓ {title}: инструкций {len(body)}, действий (первые) {len(actions)}")
        except Exception as exc:
            problems.append(f"«{title}»: ошибка исполнения — {exc}")

    recorder = NullBackend()
    engine = ScriptEngine(backend_factory=lambda dry, screen: recorder)
    preset = examples()[1]
    preset.script = "повторить 3 { клик Точка1\n ждать 10мс\n клик Точка2 }"
    if engine.start(preset, screen_size=(1920, 1080)):
        engine.join(10)
        clicks = recorder.clicks()
        if len(clicks) != 6:
            problems.append(f"движок: ожидалось 6 нажатий, получено {len(clicks)}")
        else:
            say(f"  ✓ движок: {len(clicks)} нажатий выполнено")
    else:
        problems.append("движок: не удалось запустить алгоритм")

    # страховка: алгоритм должен встать на паузу, если курсор увели вручную
    class _Desk(NullBackend):
        real = True

    from .core.models import Failsafe

    desk = _Desk()
    guard_engine = ScriptEngine(backend_factory=lambda dry, screen: desk)
    guard_preset = Preset(name="страховка")
    guard_preset.add_point(100, 200, "A")
    guard_preset.script = "цикл { клик A ждать 1с }"
    if guard_engine.start(
        guard_preset,
        screen_size=(1920, 1080),
        failsafe=Failsafe(watch_user_move=True, threshold=40),
    ):
        deadline = time.monotonic() + 5
        while not desk.clicks() and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.1)
        x, y = desk.position()
        desk._pos = (x + 300, y + 300)  # «рука пользователя»
        while not guard_engine.is_paused and time.monotonic() < deadline:
            time.sleep(0.01)
        if guard_engine.is_paused:
            say("  ✓ страховка: движение мыши ставит алгоритм на паузу")
        else:
            problems.append("страховка: движение мыши не остановило алгоритм")
        guard_engine.stop()
        guard_engine.join(3)
    else:
        problems.append("страховка: не удалось запустить проверочный алгоритм")

    from .core.backends import probe_backend

    available, message = probe_backend()
    say(f"  {'✓' if available else '!'} {message}")

    # горячие клавиши: сочетания по умолчанию должны быть корректны
    from .core.hotkeys import HotkeyManager, describe
    from .core.storage import AppConfig

    keys = AppConfig().hotkeys
    manager = HotkeyManager()
    for action, title in (
        ("start_stop", "старт/стоп"), ("pause", "пауза"),
        ("panic_stop", "остановка"), ("pick_point", "новая точка"),
    ):
        manager.bind(action, getattr(keys, action), lambda: None, title)
    manager._prepare()
    if manager.problems:
        problems.append("горячие клавиши: " + "; ".join(manager.problems))
    else:
        combos = ", ".join(describe(combo) for combo in manager.registered.values())
        say(f"  ✓ горячие клавиши разобраны: {combos}")
    if manager.start():
        say("  ✓ глобальные горячие клавиши слушаются")
        manager.stop()
    else:
        say(f"  ! {manager.status_text()}")


    try:
        from PySide6 import QtCore

        say(f"  ✓ графическая библиотека Qt {QtCore.__version__}")
    except Exception as exc:  # pragma: no cover
        problems.append(f"PySide6 недоступен: {exc}")

    if problems:
        print("\nОбнаружены проблемы:")
        for problem in problems:
            print(f"  ✗ {problem}")
        return 1
    say("\nВсё в порядке.")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dp-autoclicker", description=f"{APP_NAME} — автокликер с визуальным редактором"
    )
    parser.add_argument("preset", nargs="?", help="файл пресета для открытия")
    parser.add_argument(
        "--self-check", action="store_true", help="проверить работоспособность и выйти"
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)

    if args.self_check:
        return self_check()
    return run_gui(Path(args.preset) if args.preset else None)
