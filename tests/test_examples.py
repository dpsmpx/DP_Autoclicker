"""Готовые пресеты должны разбираться, исполняться и сохраняться."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dp_autoclicker.core.models import Preset
from dp_autoclicker.core.runtime.interpreter import collect
from dp_autoclicker.core.script.parser import parse
from dp_autoclicker.core.script.printer import to_source
from dp_autoclicker.core.templates import blank_preset, examples

PRESETS_DIR = Path(__file__).resolve().parent.parent / "presets"


@pytest.mark.parametrize("preset", examples() + [blank_preset()], ids=lambda p: p.name)
def test_example_presets_parse_and_run(preset: Preset):
    body = parse(preset.script).body
    assert body
    printed = to_source(body)
    assert to_source(parse(printed).body) == printed
    points = {p.name: p for p in preset.points}
    actions = collect(body, points, limit=300)
    assert actions


@pytest.mark.parametrize("preset", examples(), ids=lambda p: p.name)
def test_example_presets_survive_save_and_load(preset: Preset, tmp_path):
    path = preset.save(tmp_path / "p")
    restored = Preset.load(path)
    assert restored.script == preset.script
    assert [p.name for p in restored.points] == [p.name for p in preset.points]
    assert restored.randomization.enabled == preset.randomization.enabled


def test_shipped_preset_files_are_valid():
    files = sorted(PRESETS_DIR.glob("*.json"))
    assert files, "в каталоге presets/ должны лежать примеры для обмена"
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        preset = Preset.from_dict(data)
        body = parse(preset.script).body
        known = {p.name for p in preset.points}
        from dp_autoclicker.core.script.ast_nodes import used_points

        assert used_points(body) <= known, f"{path.name}: ссылки на несуществующие точки"
        collect(body, {p.name: p for p in preset.points}, limit=200)


def test_self_check_passes():
    from dp_autoclicker.app import self_check

    assert self_check(verbose=False) == 0
