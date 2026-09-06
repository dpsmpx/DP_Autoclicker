"""Рандомизация действий — «человечное» поведение.

Важно: всё выключено по умолчанию. Пока `RandomizationSettings.enabled`
равно False, координаты и паузы остаются ровно такими, как задал пользователь.
"""

from __future__ import annotations

import math
import random
from typing import Optional

from ..models import Point, RandomizationSettings

#: сколько раз пытаться подобрать позицию, отличающуюся от предыдущей
_MAX_ATTEMPTS = 16


class Randomizer:
    def __init__(
        self,
        settings: Optional[RandomizationSettings] = None,
        rng: Optional[random.Random] = None,
        screen_size: Optional[tuple[int, int]] = None,
    ) -> None:
        self.settings = settings or RandomizationSettings()
        seed = self.settings.seed or None
        self.rng = rng or random.Random(seed)
        self.screen_size = screen_size
        #: последняя выданная позиция для каждой точки
        self._last: dict[str, tuple[int, int]] = {}

    # -------------------------------------------------------------- сервис
    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    def reset(self) -> None:
        self._last.clear()

    def _clamp(self, x: int, y: int) -> tuple[int, int]:
        if not self.screen_size:
            return x, y
        w, h = self.screen_size
        return max(0, min(int(x), w - 1)), max(0, min(int(y), h - 1))

    # ------------------------------------------------------------ позиция
    def radius_for(self, point: Optional[Point]) -> float:
        """Эффективный радиус разброса для точки."""
        if not self.settings.enabled:
            return 0.0
        if point is not None and point.radius > 0:
            return point.radius
        return self.settings.position_jitter

    def _shape_for(self, point: Optional[Point]) -> str:
        if point is not None and point.shape:
            return point.shape
        return self.settings.shape

    def _sample_offset(self, radius: float, shape: str) -> tuple[float, float]:
        if radius <= 0:
            return 0.0, 0.0
        if shape == "square":
            return self.rng.uniform(-radius, radius), self.rng.uniform(-radius, radius)
        if shape == "gauss":
            sigma = radius / 2.5
            return self.rng.gauss(0.0, sigma), self.rng.gauss(0.0, sigma)
        # равномерно по кругу
        angle = self.rng.uniform(0.0, 2.0 * math.pi)
        distance = radius * math.sqrt(self.rng.random())
        return distance * math.cos(angle), distance * math.sin(angle)

    def position(
        self, x: int, y: int, point: Optional[Point] = None, key: Optional[str] = None
    ) -> tuple[int, int]:
        """Возвращает координаты нажатия с учётом разброса.

        При включённой опции «не бить дважды в одно место» позиция
        подбирается так, чтобы отличаться от предыдущей позиции этой же точки
        не менее чем на `min_separation` пикселей.
        """
        radius = self.radius_for(point)
        if radius <= 0:
            return self._clamp(x, y)

        shape = self._shape_for(point)
        key = key or (point.name if point else f"@{x},{y}")
        previous = self._last.get(key)
        need_separation = (
            self.settings.avoid_repeat and previous is not None and self.settings.min_separation > 0
        )

        best: tuple[int, int] = (x, y)
        best_distance = -1.0
        for _ in range(_MAX_ATTEMPTS if need_separation else 1):
            dx, dy = self._sample_offset(radius, shape)
            candidate = self._clamp(int(round(x + dx)), int(round(y + dy)))
            if not need_separation:
                best = candidate
                break
            distance = math.dist(candidate, previous)  # type: ignore[arg-type]
            if distance > best_distance:
                best, best_distance = candidate, distance
            if distance >= self.settings.min_separation:
                break
        self._last[key] = best
        return best

    # -------------------------------------------------------------- время
    def delay(self, seconds: float) -> float:
        """Разброс паузы: ±delay_jitter."""
        if not self.settings.enabled or seconds <= 0 or self.settings.delay_jitter <= 0:
            return max(0.0, seconds)
        jitter = self.settings.delay_jitter
        return max(0.0, seconds * self.rng.uniform(1.0 - jitter, 1.0 + jitter))

    def hold_time(self) -> float:
        """Длительность удержания кнопки мыши, секунды."""
        if not self.settings.enabled:
            return 0.0
        return self.rng.uniform(self.settings.hold_min_ms, self.settings.hold_max_ms) / 1000.0

    def click_gap(self) -> float:
        """Пауза между повторными кликами одной инструкции."""
        if not self.settings.enabled:
            return 0.02
        return self.rng.uniform(self.settings.hold_min_ms, self.settings.hold_max_ms * 2) / 1000.0

    def move_duration(self) -> float:
        if not self.settings.enabled or not self.settings.humanize_move:
            return 0.0
        return (
            self.rng.uniform(
                self.settings.move_duration_min_ms, self.settings.move_duration_max_ms
            )
            / 1000.0
        )

    def idle_pause(self) -> float:
        """Иногда «отвлекаемся» на случайную паузу."""
        if not self.settings.enabled or self.settings.idle_chance <= 0:
            return 0.0
        if self.rng.random() >= self.settings.idle_chance:
            return 0.0
        return self.rng.uniform(self.settings.idle_min_ms, self.settings.idle_max_ms) / 1000.0

    def chance(self, probability: float) -> bool:
        return self.rng.random() < probability

    def uniform(self, low: float, high: float) -> float:
        if high < low:
            low, high = high, low
        return self.rng.uniform(low, high)

    # ------------------------------------------------------------ движение
    def move_path(
        self, start: tuple[int, int], end: tuple[int, int], humanize: Optional[bool] = None
    ) -> list[tuple[int, int]]:
        """Строит траекторию курсора: кривая Безье с плавным ускорением."""
        if humanize is None:
            humanize = self.settings.enabled and self.settings.humanize_move
        if not humanize:
            return [end]
        steps = max(2, self.settings.move_steps)
        (x0, y0), (x1, y1) = start, end
        distance = math.dist(start, end)
        if distance < 2:
            return [end]
        # контрольная точка смещена перпендикулярно отрезку
        bow = min(distance * 0.22, 140.0)
        offset = self.rng.uniform(-bow, bow)
        mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        nx, ny = -(y1 - y0) / distance, (x1 - x0) / distance
        cx, cy = mx + nx * offset, my + ny * offset

        path: list[tuple[int, int]] = []
        for i in range(1, steps + 1):
            t = i / steps
            # сглаживание: медленный старт и медленное окончание
            te = t * t * (3.0 - 2.0 * t)
            inv = 1.0 - te
            px = inv * inv * x0 + 2 * inv * te * cx + te * te * x1
            py = inv * inv * y0 + 2 * inv * te * cy + te * te * y1
            path.append(self._clamp(int(round(px)), int(round(py))))
        path[-1] = self._clamp(int(x1), int(y1))
        return path
