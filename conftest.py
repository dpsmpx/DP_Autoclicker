"""Общая настройка тестов: графика в offscreen, домашний каталог во временном."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Тесты интерфейса должны работать без монитора.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Настройки и пресеты не должны попадать в реальный каталог пользователя.
os.environ["HOME"] = tempfile.mkdtemp(prefix="dp-autoclicker-tests-")
