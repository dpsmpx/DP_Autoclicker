"""Готовые примеры пресетов — стартовая точка для пользователя."""

from __future__ import annotations

from .models import Point, Preset, RandomizationSettings, RunSettings

_SIMPLE = """# Простой автокликер: бесконечные клики с паузой
цикл {
    клик Точка1
    ждать 500мс
}
"""

_DOUBLE = """# Чередование двух точек со случайной паузой
цикл {
    клик Точка1
    ждать 300мс..700мс
    клик Точка2
    ждать 300мс..700мс
}
"""

_FARM = """# Пример сложного алгоритма: серия действий с условиями
повторить 20 раз {
    клик Кнопка_действия
    ждать 400мс..900мс

    # каждый пятый круг — дополнительная проверка
    если итерация остаток 5 == 0 {
        клик Кнопка_проверки кнопкой правая
        ждать 1с
        клавиша esc
    }

    # изредка делаем вид, что отвлеклись
    если шанс(15%) {
        ждать 2с..4с
    }
}
сообщение "Цикл завершён"
"""


def blank_preset(width: int = 1920, height: int = 1080) -> Preset:
    """Пустой пресет с двумя точками по центру экрана."""
    preset = Preset(name="Новый пресет")
    preset.screen.width, preset.screen.height = width, height
    preset.points = [
        Point(name="Точка1", x=width // 2, y=height // 2, color="#5B8CFF"),
        Point(name="Точка2", x=width // 2 + 140, y=height // 2 + 90, color="#4ED6A1"),
    ]
    preset.script = _SIMPLE
    return preset


def examples(width: int = 1920, height: int = 1080) -> list[Preset]:
    """Набор демонстрационных пресетов."""
    cx, cy = width // 2, height // 2

    simple = Preset(
        name="Простой автокликер",
        description="Бесконечные клики в одну точку с паузой 500 мс.",
        author="DP Autoclicker",
        tags=["базовый"],
        script=_SIMPLE,
    )
    simple.points = [Point(name="Точка1", x=cx, y=cy)]

    duo = Preset(
        name="Две точки по очереди",
        description="Кликает поочерёдно в две точки со случайной паузой.",
        author="DP Autoclicker",
        tags=["базовый", "случайность"],
        script=_DOUBLE,
        randomization=RandomizationSettings(enabled=True, position_jitter=5.0),
    )
    duo.points = [
        Point(name="Точка1", x=cx - 120, y=cy, color="#5B8CFF"),
        Point(name="Точка2", x=cx + 120, y=cy, color="#4ED6A1"),
    ]

    complex_preset = Preset(
        name="Сложный сценарий",
        description="Условия, счётчик итераций и случайные задержки.",
        author="DP Autoclicker",
        tags=["продвинутый"],
        script=_FARM,
        randomization=RandomizationSettings(
            enabled=True, position_jitter=6.0, humanize_move=True, idle_chance=0.1
        ),
        run=RunSettings(start_delay=3.0),
    )
    complex_preset.points = [
        Point(name="Кнопка_действия", x=cx, y=cy + 160, color="#FFC46B"),
        Point(name="Кнопка_проверки", x=cx + 240, y=cy - 120, color="#FF6B7A"),
    ]

    for preset in (simple, duo, complex_preset):
        preset.screen.width, preset.screen.height = width, height
    return [simple, duo, complex_preset]
