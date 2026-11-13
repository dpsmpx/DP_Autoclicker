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
VERSION = "1.0.1"


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
            roundtrip = to_source(body)
            parse(roundtrip)
        except Exception as exc:
            problems.append(f"«{title}»: round-trip скрипта — {exc}")
            continue
        try:
            engine = ScriptEngine(backend=NullBackend())
            engine.load(preset)
            engine.start()
            deadline = time.monotonic() + 2.0
            while engine.is_running and time.monotonic() < deadline:
                time.sleep(0.05)
            engine.stop()
        except Exception as exc:
            problems.append(f"«{title}»: прогон — {exc}")
            continue
        say(f"  ✓ {title}")

    try:
        from PySide6 import QtCore  # noqa: F401

        say("  ✓ PySide6 доступен")
    except Exception as exc:
        problems.append(f"PySide6 недоступен: {exc}")

    try:
        import pynput  # noqa: F401

        say("  ✓ pynput доступен")
    except Exception as exc:
        problems.append(f"pynput недоступен: {exc}")

    if problems:
        say("\nОбнаружены проблемы:")
        for item in problems:
            say(f"  ✗ {item}")
        return 1
    say("\nВсё в порядке.")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="dp-autoclicker", description=APP_NAME)
    parser.add_argument("--self-check", action="store_true", help="быстрая самопроверка")
    parser.add_argument("--preset", type=Path, help="открыть пресет при старте")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    args = parser.parse_args(argv)
    if args.self_check:
        return self_check()
    return run_gui(args.preset)


if __name__ == "__main__":
    raise SystemExit(main())
