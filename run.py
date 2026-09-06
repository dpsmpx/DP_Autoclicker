#!/usr/bin/env python3
"""Запуск DP Autoclicker из исходников: python run.py"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dp_autoclicker.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
