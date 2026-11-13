#!/usr/bin/env python3
"""Точка входа DP Autoclicker.

Используется и для ``python DP_Autoclicker.py``, и как скрипт PyInstaller
(``--onefile --windowed``): в .exe уже встроены Python, PySide6 и pynput,
отдельная установка Python не нужна.
"""

from __future__ import annotations

import sys


def main() -> int:
    from dp_autoclicker.app import main as run_app

    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
