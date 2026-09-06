"""Точки, пресеты, сохранение и перенос между экранами."""

from __future__ import annotations

import json

import pytest

from dp_autoclicker.core.models import (
    Point,
    Preset,
    RandomizationSettings,
    ValidationError,
    rename_in_script,
)


def test_point_validation_rejects_bad_names():
    Point(name="Кнопка_ОК").validate()
    Point(name="btn2").validate()
    with pytest.raises(ValidationError):
        Point(name="2точка").validate()
    with pytest.raises(ValidationError):
        Point(name="моя точка").validate()
    with pytest.raises(ValidationError):
        # имя занято ключевым словом языка
        Point(name="клик").validate()


def test_preset_add_point_generates_unique_names():
    preset = Preset()
    first = preset.add_point(10, 20)
    second = preset.add_point(30, 40)
    assert first.name != second.name
    with pytest.raises(ValidationError):
        preset.add_point(1, 1, first.name)


def test_rename_point_updates_script_but_not_strings_and_comments():
    script = 'клик A\nлог "A остаётся"\n# A остаётся\nклик AB'
    assert rename_in_script(script, "A", "Б") == (
        'клик Б\nлог "A остаётся"\n# A остаётся\nклик AB'
    )


def test_preset_json_roundtrip():
    preset = Preset(name="Тест", author="Кто-то", description="описание", tags=["a", "b"])
    preset.add_point(100, 200, "Точка_А")
    preset.points[0].radius = 5.5
    preset.script = "клик Точка_А"
    preset.randomization = RandomizationSettings(enabled=True, position_jitter=7)
    preset.screen.width, preset.screen.height = 1920, 1080

    restored = Preset.from_json(preset.to_json())
    assert restored.name == preset.name
    assert restored.tags == ["a", "b"]
    assert restored.points[0].radius == 5.5
    assert restored.randomization.enabled is True
    assert restored.randomization.position_jitter == 7


def test_preset_from_dict_ignores_unknown_keys_and_coerces_types():
    data = {
        "format": "dp-autoclicker-preset",
        "version": 1,
        "name": "Из будущего",
        "points": [{"name": "A", "x": "12.7", "y": 40}],
        "randomization": {"enabled": "да", "move_steps": "12"},
        "неизвестное_поле": {"вложенное": 1},
    }
    preset = Preset.from_dict(data)
    assert preset.points[0].x == 13
    assert preset.randomization.enabled is True
    assert preset.randomization.move_steps == 12


def test_preset_rejects_foreign_format_and_newer_version():
    with pytest.raises(ValidationError):
        Preset.from_dict({"format": "чужой", "name": "x"})
    with pytest.raises(ValidationError):
        Preset.from_dict({"format": "dp-autoclicker-preset", "version": 99, "name": "x"})


def test_preset_rejects_broken_json():
    with pytest.raises(ValidationError):
        Preset.from_json("{не json")


def test_rescale_moves_points_to_new_resolution():
    preset = Preset()
    preset.screen.width, preset.screen.height = 1920, 1080
    preset.add_point(960, 540, "Центр")
    assert preset.needs_rescale(1280, 720) is True
    preset.rescale(1280, 720)
    assert preset.points[0].pos == (640, 360)
    assert preset.needs_rescale(1280, 720) is False


def test_save_and_load(tmp_path):
    preset = Preset(name="Файловый")
    preset.add_point(1, 2, "A")
    path = preset.save(tmp_path / "мой")
    assert path.name == "мой.dpclick.json"
    assert json.loads(path.read_text(encoding="utf-8"))["name"] == "Файловый"
    assert Preset.load(path).points[0].name == "A"


def test_duplicate_point_names_are_rejected_on_load():
    data = {
        "format": "dp-autoclicker-preset",
        "points": [{"name": "A", "x": 1, "y": 1}, {"name": "A", "x": 2, "y": 2}],
    }
    with pytest.raises(ValidationError):
        Preset.from_dict(data)
