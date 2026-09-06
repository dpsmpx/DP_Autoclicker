"""Хранилище: библиотека пресетов и настройки приложения."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Optional

from .models import (
    PRESET_SUFFIX,
    Failsafe,
    Hotkeys,
    Preset,
    ValidationError,
    _from_mapping,
    _as_dict,
)

APP_DIR_NAME = ".dp_autoclicker"


def app_dir() -> Path:
    """Каталог с данными пользователя."""
    return Path.home() / APP_DIR_NAME


def presets_dir() -> Path:
    path = app_dir() / "presets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return app_dir() / "config.json"


def safe_filename(name: str) -> str:
    """Превращает название пресета в безопасное имя файла."""
    cleaned = re.sub(r"[^\w\s.-]", "", name, flags=re.UNICODE).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned or "preset"


@dataclass
class WindowState:
    """Положение и вид плавающего окна."""

    x: int = -1
    y: int = -1
    width: int = 460
    height: int = 620
    opacity: float = 0.94
    always_on_top: bool = True
    compact: bool = False
    #: не перехватывать мышь во время работы алгоритма
    click_through_when_running: bool = True

    def __post_init__(self) -> None:
        self.opacity = min(max(0.35, float(self.opacity)), 1.0)
        self.width = max(360, int(self.width))
        self.height = max(320, int(self.height))


@dataclass
class AppConfig:
    """Настройки самой программы (не переносятся вместе с пресетом)."""

    author: str = ""
    #: язык ключевых слов в редакторе скрипта: ru или en
    dialect: str = "ru"
    accent: str = "#5B8CFF"
    window: WindowState = field(default_factory=WindowState)
    hotkeys: Hotkeys = field(default_factory=Hotkeys)
    failsafe: Failsafe = field(default_factory=Failsafe)
    last_preset: str = ""
    show_hints: bool = True

    def __post_init__(self) -> None:
        if self.dialect not in ("ru", "en"):
            self.dialect = "ru"

    # ------------------------------------------------------------- файлы
    @classmethod
    def load(cls, path: Optional[Path] = None) -> "AppConfig":
        path = path or config_path()
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        config = cls()
        for f in fields(cls):
            if f.name not in data or data[f.name] is None:
                continue
            if f.name == "window":
                config.window = _from_mapping(WindowState, data[f.name])
            elif f.name == "hotkeys":
                config.hotkeys = _from_mapping(Hotkeys, data[f.name])
            elif f.name == "failsafe":
                config.failsafe = _from_mapping(Failsafe, data[f.name])
            else:
                setattr(config, f.name, data[f.name])
        config.__post_init__()
        return config

    def save(self, path: Optional[Path] = None) -> Path:
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(_as_dict(self), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(path)
        return path


@dataclass
class PresetEntry:
    """Строка библиотеки пресетов."""

    path: Path
    name: str
    description: str = ""
    author: str = ""
    points: int = 0
    modified: str = ""


class PresetLibrary:
    """Папка с пресетами пользователя."""

    def __init__(self, directory: Optional[Path] = None) -> None:
        self.directory = Path(directory) if directory else presets_dir()
        self.directory.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[PresetEntry]:
        entries: list[PresetEntry] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            entries.append(
                PresetEntry(
                    path=path,
                    name=str(data.get("name") or path.stem),
                    description=str(data.get("description") or ""),
                    author=str(data.get("author") or ""),
                    points=len(data.get("points") or []),
                    modified=str(data.get("modified") or ""),
                )
            )
        entries.sort(key=lambda e: e.modified, reverse=True)
        return entries

    def path_for(self, preset: Preset) -> Path:
        return self.directory / (safe_filename(preset.name) + PRESET_SUFFIX)

    def save(self, preset: Preset, path: Optional[Path] = None) -> Path:
        return preset.save(path or self.path_for(preset))

    def load(self, path: Path) -> Preset:
        return Preset.load(path)

    def delete(self, path: Path) -> None:
        try:
            Path(path).unlink()
        except OSError as exc:
            raise ValidationError(f"Не удалось удалить файл: {exc}") from exc

    def exists(self, preset: Preset) -> bool:
        return self.path_for(preset).exists()
