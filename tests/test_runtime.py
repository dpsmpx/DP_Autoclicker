"""Интерпретатор и рандомизация."""

from __future__ import annotations

import math

import pytest

from dp_autoclicker.core.models import Point, RandomizationSettings, RunSettings
from dp_autoclicker.core.runtime import actions as act
from dp_autoclicker.core.runtime.interpreter import collect
from dp_autoclicker.core.runtime.randomizer import Randomizer
from dp_autoclicker.core.script.errors import RuntimeScriptError
from dp_autoclicker.core.script.parser import parse

POINTS = {
    "A": Point(name="A", x=100, y=200),
    "B": Point(name="B", x=300, y=400),
}


def run(source: str, **kwargs):
    return collect(parse(source).body, POINTS, **kwargs)


def clicks(source: str, **kwargs):
    return [a for a in run(source, **kwargs) if isinstance(a, act.ClickAt)]


def test_click_uses_point_coordinates():
    (click,) = clicks("клик A")
    assert (click.x, click.y) == (100, 200)
    assert click.button == "left"


def test_click_repeats_and_button():
    result = clicks("клик B кнопкой пкм раз 3")
    assert len(result) == 3
    assert {c.button for c in result} == {"right"}
    assert {(c.x, c.y) for c in result} == {(300, 400)}


def test_repeat_and_iteration_variable():
    actions = run("повторить 3 { клик @(итерация, 0) }")
    assert [(a.x, a.y) for a in actions if isinstance(a, act.ClickAt)] == [
        (1, 0), (2, 0), (3, 0)
    ]


def test_if_else_branches():
    assert len(clicks("если да { клик A } иначе { клик B клик B }")) == 1
    assert len(clicks("если нет { клик A } иначе { клик B клик B }")) == 2


def test_while_loop_with_variable():
    actions = clicks("пусть i = 0\nпока i < 4 { пусть i = i + 1  клик A }")
    assert len(actions) == 4


def test_break_exits_the_loop_immediately():
    actions = clicks("повторить 3 { клик A прервать клик B }")
    assert len(actions) == 1
    assert (actions[0].x, actions[0].y) == (100, 200)


def test_break_leaves_only_the_inner_loop():
    # внешний цикл должен отработать все три раза, внутренний — прерваться сразу
    actions = clicks("повторить 3 { повторить 5 { клик A прервать } клик B }")
    assert [(a.x, a.y) for a in actions] == [
        (100, 200), (300, 400), (100, 200), (300, 400), (100, 200), (300, 400)
    ]


def test_stop_ends_program():
    actions = clicks("клик A стоп клик B")
    assert len(actions) == 1


def test_wait_becomes_sleep_in_seconds():
    sleeps = [a for a in run("ждать 250мс") if isinstance(a, act.Sleep)]
    assert sleeps[0].seconds == pytest.approx(0.25)


def test_speed_multiplier_shortens_pauses():
    actions = collect(
        parse("ждать 1с").body, POINTS, run=RunSettings(speed=2.0)
    )
    assert actions[0].seconds == pytest.approx(0.5)


def test_range_produces_value_inside_bounds():
    for _ in range(20):
        sleeps = [a for a in run("ждать 100мс..300мс") if isinstance(a, act.Sleep)]
        assert 0.1 <= sleeps[0].seconds <= 0.3


def test_drag_emits_press_move_release():
    kinds = [type(a).__name__ for a in run("перетащить A к B за 100мс")]
    assert kinds == ["MoveTo", "MouseDown", "MoveTo", "MouseUp"]


def test_keys_scroll_and_text():
    actions = run('клавиша ctrl+c\nпрокрутить -3 на A\nпечатать "тест"')
    assert any(isinstance(a, act.KeyTap) and a.combo == "ctrl+c" for a in actions)
    assert any(isinstance(a, act.ScrollBy) and a.dy == -3 for a in actions)
    assert any(isinstance(a, act.TypeText) and a.text == "тест" for a in actions)


def test_missing_point_is_reported_with_line():
    with pytest.raises(RuntimeScriptError) as info:
        run("клик A\nклик Нету")
    assert info.value.line == 2
    assert "Нету" in str(info.value)


def test_unknown_variable_and_division_by_zero():
    with pytest.raises(RuntimeScriptError):
        run("ждать x")
    with pytest.raises(RuntimeScriptError):
        run("ждать 1с / 0")


def test_empty_infinite_loop_is_caught():
    with pytest.raises(RuntimeScriptError) as info:
        run("цикл { пусть x = 1 }", limit=50)
    assert "цикл" in str(info.value).lower()


def test_max_actions_limit_stops_program():
    actions = collect(
        parse("цикл { клик A }").body, POINTS, run=RunSettings(max_actions=5), limit=100
    )
    assert len([a for a in actions if isinstance(a, act.ClickAt)]) == 5


def test_log_message_renders_values():
    actions = run('сообщение "кликов: " + действий')
    assert isinstance(actions[-1], act.LogMessage)
    assert actions[-1].message == "кликов: 0"


# ------------------------------------------------------------- рандомизация
def test_randomization_disabled_keeps_exact_coordinates():
    settings = RandomizationSettings(enabled=False, position_jitter=20)
    randomizer = Randomizer(settings)
    point = Point(name="A", x=500, y=500)
    assert {randomizer.position(500, 500, point) for _ in range(10)} == {(500, 500)}
    assert randomizer.delay(0.5) == 0.5
    assert randomizer.hold_time() == 0.0


def test_randomization_stays_inside_radius():
    settings = RandomizationSettings(enabled=True, position_jitter=10, seed=1)
    randomizer = Randomizer(settings)
    point = Point(name="A", x=500, y=500)
    for _ in range(200):
        x, y = randomizer.position(500, 500, point)
        assert math.dist((x, y), (500, 500)) <= 11


def test_avoid_repeat_keeps_minimum_distance():
    settings = RandomizationSettings(
        enabled=True, position_jitter=12, avoid_repeat=True, min_separation=5, seed=3
    )
    randomizer = Randomizer(settings)
    point = Point(name="A", x=400, y=400)
    positions = [randomizer.position(400, 400, point) for _ in range(60)]
    gaps = [math.dist(positions[i], positions[i + 1]) for i in range(len(positions) - 1)]
    assert min(gaps) >= 5
    assert len(set(positions)) > 20


def test_point_radius_overrides_global_jitter():
    settings = RandomizationSettings(enabled=True, position_jitter=0, seed=5)
    randomizer = Randomizer(settings)
    exact = Point(name="A", x=100, y=100)
    spread = Point(name="B", x=100, y=100, radius=15)
    assert randomizer.position(100, 100, exact) == (100, 100)
    positions = {randomizer.position(100, 100, spread) for _ in range(30)}
    assert len(positions) > 5


def test_delay_jitter_bounds_and_seed_reproducibility():
    settings = RandomizationSettings(enabled=True, delay_jitter=0.2, seed=42)
    values_a = [Randomizer(settings).delay(1.0) for _ in range(3)]
    values_b = [Randomizer(settings).delay(1.0) for _ in range(3)]
    assert values_a == values_b
    assert all(0.8 <= v <= 1.2 for v in values_a)


def test_position_is_clamped_to_screen():
    settings = RandomizationSettings(enabled=True, position_jitter=50, seed=9)
    randomizer = Randomizer(settings, screen_size=(800, 600))
    for _ in range(50):
        x, y = randomizer.position(5, 5, Point(name="A", x=5, y=5))
        assert 0 <= x < 800 and 0 <= y < 600


def test_move_path_starts_and_ends_correctly():
    settings = RandomizationSettings(enabled=True, humanize_move=True, move_steps=10, seed=2)
    path = Randomizer(settings).move_path((0, 0), (200, 100))
    assert len(path) == 10
    assert path[-1] == (200, 100)


def test_humanized_click_carries_path():
    settings = RandomizationSettings(enabled=True, humanize_move=True, seed=4)
    actions = collect(
        parse("клик A").body, POINTS, randomizer=Randomizer(settings), cursor=(0, 0)
    )
    assert len(actions[0].path) > 1
