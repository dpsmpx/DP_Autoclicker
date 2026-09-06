"""Модели данных DP Autoclicker.

Модуль полностью независим от GUI и от библиотек ввода: его можно
импортировать в тестах, в CLI и в любом окружении без экрана.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PRESET_FORMAT = "dp-autoclicker-preset"
PRESET_VERSION = 1
PRESET_SUFFIX = ".dpclick.json"

BUTTONS = ("left", "right", "middle")
SHAPES = ("circle", "square", "gauss")

#: Имя точки должно быть идентификатором, чтобы на него можно было
#: сослаться из скрипта. Разрешаем кириллицу — так удобнее русскому пользователю.
NAME_RE = re.compile(r"^[A-Za-zЀ-ӿ_][A-Za-z0-9Ѐ-ӿ_]*$")


class ValidationError(ValueError):
    """Ошибка проверки данных пресета."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _short_id() -> str:
    return uuid.uuid4().hex[:8]


def _coerce(value: Any, target_type: Any) -> Any:
    """Мягкое приведение типа при загрузке чужого пресета."""
    if target_type is bool:
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "да", "on")
        return bool(value)
    if target_type is int:
        return int(round(float(value)))
    if target_type is float:
        return float(value)
    if target_type is str:
        return str(value)
    return value


#: `from __future__ import annotations` превращает аннотации в строки,
#: поэтому простые типы полей разрешаем по имени.
_SCALARS: dict[str, type] = {"bool": bool, "int": int, "float": float, "str": str}


def _field_type(f: Any) -> Any:
    """Возвращает реальный тип поля dataclass (аннотации хранятся строками)."""
    if isinstance(f.type, str):
        return _SCALARS.get(f.type.strip())
    return f.type


def _from_mapping(cls: type, data: Any) -> Any:
    """Создаёт dataclass из словаря, игнорируя незнакомые ключи.

    Незнакомые ключи игнорируются намеренно: пресет, сохранённый более новой
    версией программы, всё равно должен открыться.
    """
    if not isinstance(data, dict):
        raise ValidationError(f"Ожидался объект для {cls.__name__}, получено {type(data).__name__}")
    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        if f.name not in data:
            continue
        raw = data[f.name]
        if raw is None:
            continue
        ftype = _field_type(f)
        try:
            if isinstance(ftype, type) and is_dataclass(ftype):
                kwargs[f.name] = _from_mapping(ftype, raw)
            elif ftype in (bool, int, float, str):
                kwargs[f.name] = _coerce(raw, ftype)
            else:
                kwargs[f.name] = raw
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"Поле «{f.name}» имеет неверное значение: {raw!r}") from exc
    return cls(**kwargs)


def _as_dict(obj: Any) -> Any:
    if is_dataclass(obj):
        return {f.name: _as_dict(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, (list, tuple)):
        return [_as_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _as_dict(v) for k, v in obj.items()}
    return obj


@dataclass
class Point:
    """Именованная точка нажатия на экране."""

    name: str
    x: int = 0
    y: int = 0
    #: Радиус разброса в пикселях для конкретной точки. 0 — брать значение
    #: из глобальных настроек рандомизации.
    radius: float = 0.0
    #: Форма области разброса: circle / square / gauss. Пусто — из настроек.
    shape: str = ""
    color: str = "#5B8CFF"
    note: str = ""
    id: str = field(default_factory=_short_id)

    def __post_init__(self) -> None:
        self.x = int(self.x)
        self.y = int(self.y)
        self.radius = max(0.0, float(self.radius))
        if self.shape and self.shape not in SHAPES:
            raise ValidationError(f"Неизвестная форма разброса: {self.shape}")

    def validate(self) -> None:
        from .script.keywords import is_reserved

        if not NAME_RE.match(self.name):
            raise ValidationError(
                f"Недопустимое имя точки «{self.name}»: разрешены буквы, цифры и «_», "
                "первый символ — не цифра"
            )
        if is_reserved(self.name):
            raise ValidationError(
                f"Имя «{self.name}» занято языком алгоритма — выберите другое"
            )

    @property
    def pos(self) -> tuple[int, int]:
        return (self.x, self.y)

    def copy(self) -> "Point":
        return Point(**{**_as_dict(self), "id": _short_id()})


@dataclass
class RandomizationSettings:
    """Настройки «очеловечивания».

    По умолчанию всё выключено: рандомизация — это опция, а не основное
    поведение (см. `enabled`).
    """

    enabled: bool = False
    #: Радиус разброса координат по умолчанию, пиксели.
    position_jitter: float = 4.0
    shape: str = "circle"
    #: Не бить дважды в одну и ту же позицию одной точки.
    avoid_repeat: bool = True
    #: Минимальное расстояние между двумя подряд идущими нажатиями, пиксели.
    min_separation: float = 3.0
    #: Разброс пауз, доля от длительности (0.15 = ±15 %).
    delay_jitter: float = 0.15
    #: Удержание кнопки между нажатием и отпусканием, мс.
    hold_min_ms: float = 20.0
    hold_max_ms: float = 70.0
    #: Плавное перемещение курсора вместо телепортации.
    humanize_move: bool = False
    move_duration_min_ms: float = 90.0
    move_duration_max_ms: float = 240.0
    move_steps: int = 24
    #: Вероятность «отвлечься» — случайная длинная пауза, доля 0..1.
    idle_chance: float = 0.0
    idle_min_ms: float = 400.0
    idle_max_ms: float = 1500.0
    #: Фиксированное зерно генератора для воспроизводимости. 0 — случайное.
    seed: int = 0

    def __post_init__(self) -> None:
        if self.shape not in SHAPES:
            raise ValidationError(f"Неизвестная форма разброса: {self.shape}")
        self.position_jitter = max(0.0, float(self.position_jitter))
        self.min_separation = max(0.0, float(self.min_separation))
        self.delay_jitter = min(max(0.0, float(self.delay_jitter)), 1.0)
        self.idle_chance = min(max(0.0, float(self.idle_chance)), 1.0)
        self.move_steps = max(2, int(self.move_steps))
        if self.hold_max_ms < self.hold_min_ms:
            self.hold_min_ms, self.hold_max_ms = self.hold_max_ms, self.hold_min_ms
        if self.move_duration_max_ms < self.move_duration_min_ms:
            self.move_duration_min_ms, self.move_duration_max_ms = (
                self.move_duration_max_ms,
                self.move_duration_min_ms,
            )
        if self.idle_max_ms < self.idle_min_ms:
            self.idle_min_ms, self.idle_max_ms = self.idle_max_ms, self.idle_min_ms


@dataclass
class RunSettings:
    """Параметры запуска алгоритма."""

    #: Множитель скорости: 2.0 — паузы вдвое короче.
    speed: float = 1.0
    #: Сухой прогон: действия только логируются, реального ввода нет.
    dry_run: bool = False
    #: Обратный отсчёт перед стартом, секунды.
    start_delay: float = 0.0
    #: Ограничения безопасности. 0 — без ограничения.
    max_runtime: float = 0.0
    max_actions: int = 0
    #: Делать окно «прозрачным для мыши» на время работы.
    click_through_when_running: bool = True

    def __post_init__(self) -> None:
        self.speed = min(max(0.05, float(self.speed)), 20.0)
        self.start_delay = max(0.0, float(self.start_delay))
        self.max_runtime = max(0.0, float(self.max_runtime))
        self.max_actions = max(0, int(self.max_actions))


@dataclass
class Failsafe:
    """Страховка: что делать, если пользователь сам взялся за мышь.

    Настройка машины, а не пресета: чужой пресет не должен отключать
    вашу защиту, поэтому она хранится в настройках программы.
    """

    #: следить за тем, что курсор остался там, куда его поставил алгоритм
    watch_user_move: bool = True
    #: на сколько пикселей курсор должен уехать, чтобы это считалось вмешательством
    threshold: float = 40.0
    #: True — полная остановка, False — пауза с возможностью продолжить
    stop_instead_of_pause: bool = False

    def __post_init__(self) -> None:
        self.threshold = min(max(5.0, float(self.threshold)), 500.0)


@dataclass
class Hotkeys:
    """Глобальные горячие клавиши."""

    start_stop: str = "f6"
    pause: str = "f7"
    panic_stop: str = "f8"
    pick_point: str = "f2"

    def as_map(self) -> dict[str, str]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass
class ScreenRef:
    """Разрешение экрана, на котором пресет создавался."""

    width: int = 0
    height: int = 0

    def is_known(self) -> bool:
        return self.width > 0 and self.height > 0


@dataclass
class Preset:
    """Пресет — самодостаточный, переносимый набор точек и алгоритма."""

    name: str = "Новый пресет"
    description: str = ""
    author: str = ""
    tags: list[str] = field(default_factory=list)
    points: list[Point] = field(default_factory=list)
    script: str = ""
    randomization: RandomizationSettings = field(default_factory=RandomizationSettings)
    run: RunSettings = field(default_factory=RunSettings)
    screen: ScreenRef = field(default_factory=ScreenRef)
    created: str = field(default_factory=_utcnow)
    modified: str = field(default_factory=_utcnow)

    # ------------------------------------------------------------------ точки
    def point_by_name(self, name: str) -> Optional[Point]:
        for p in self.points:
            if p.name == name:
                return p
        return None

    def unique_name(self, base: str = "Точка") -> str:
        existing = {p.name for p in self.points}
        i = 1
        while f"{base}{i}" in existing:
            i += 1
        return f"{base}{i}"

    def add_point(self, x: int, y: int, name: str | None = None) -> Point:
        point = Point(name=name or self.unique_name(), x=x, y=y)
        point.validate()
        if self.point_by_name(point.name):
            raise ValidationError(f"Точка с именем «{point.name}» уже существует")
        self.points.append(point)
        return point

    def rename_point(self, point: Point, new_name: str) -> None:
        new_name = new_name.strip()
        if new_name == point.name:
            return
        probe = Point(name=new_name, x=point.x, y=point.y)
        probe.validate()
        if self.point_by_name(new_name):
            raise ValidationError(f"Точка с именем «{new_name}» уже существует")
        old = point.name
        point.name = new_name
        self.script = rename_in_script(self.script, old, new_name)

    def remove_point(self, point: Point) -> None:
        self.points = [p for p in self.points if p.id != point.id]

    # -------------------------------------------------------------- перенос
    def rescale(self, width: int, height: int) -> "Preset":
        """Пересчитывает координаты точек под другое разрешение экрана."""
        if not self.screen.is_known() or width <= 0 or height <= 0:
            return self
        kx = width / self.screen.width
        ky = height / self.screen.height
        for p in self.points:
            p.x = int(round(p.x * kx))
            p.y = int(round(p.y * ky))
        self.screen = ScreenRef(width, height)
        return self

    def needs_rescale(self, width: int, height: int) -> bool:
        return (
            self.screen.is_known()
            and width > 0
            and height > 0
            and (self.screen.width, self.screen.height) != (width, height)
        )

    def validate(self) -> None:
        seen: set[str] = set()
        for p in self.points:
            p.validate()
            if p.name in seen:
                raise ValidationError(f"Дублирующееся имя точки: «{p.name}»")
            seen.add(p.name)

    # --------------------------------------------------------- сериализация
    def to_dict(self) -> dict[str, Any]:
        data = _as_dict(self)
        return {"format": PRESET_FORMAT, "version": PRESET_VERSION, **data}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Preset":
        if not isinstance(data, dict):
            raise ValidationError("Файл пресета повреждён: ожидался объект JSON")
        fmt = data.get("format")
        if fmt is not None and fmt != PRESET_FORMAT:
            raise ValidationError(f"Это не пресет DP Autoclicker (format={fmt!r})")
        version = int(data.get("version", PRESET_VERSION) or PRESET_VERSION)
        if version > PRESET_VERSION:
            raise ValidationError(
                f"Пресет создан более новой версией программы (v{version}). Обновите DP Autoclicker."
            )
        preset = cls(
            name=str(data.get("name") or "Пресет"),
            description=str(data.get("description") or ""),
            author=str(data.get("author") or ""),
            tags=[str(t) for t in (data.get("tags") or [])],
            script=str(data.get("script") or ""),
            created=str(data.get("created") or _utcnow()),
            modified=str(data.get("modified") or _utcnow()),
        )
        for raw_point in data.get("points") or []:
            preset.points.append(_from_mapping(Point, raw_point))
        if data.get("randomization"):
            preset.randomization = _from_mapping(RandomizationSettings, data["randomization"])
        if data.get("run"):
            preset.run = _from_mapping(RunSettings, data["run"])
        if data.get("screen"):
            preset.screen = _from_mapping(ScreenRef, data["screen"])
        preset.validate()
        return preset

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "Preset":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Не удалось разобрать JSON: {exc.msg} (строка {exc.lineno})") from exc
        return cls.from_dict(data)

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        if path.suffix == "":
            path = path.with_name(path.name + PRESET_SUFFIX)
        self.modified = _utcnow()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(self.to_json(), encoding="utf-8")
        tmp.replace(path)
        return path

    @classmethod
    def load(cls, path: str | Path) -> "Preset":
        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValidationError(f"Не удалось прочитать файл: {exc}") from exc
        return cls.from_json(text)

    def copy(self) -> "Preset":
        return Preset.from_dict(self.to_dict())


def rename_in_script(script: str, old: str, new: str) -> str:
    """Переименовывает точку в тексте скрипта, не трогая строковые литералы."""
    if not script or old == new:
        return script
    pattern = re.compile(rf"(?<![A-Za-z0-9_Ѐ-ӿ]){re.escape(old)}(?![A-Za-z0-9_Ѐ-ӿ])")
    out: list[str] = []
    in_string = False
    buf: list[str] = []

    def flush() -> None:
        if buf:
            out.append(pattern.sub(new, "".join(buf)))
            buf.clear()

    i = 0
    while i < len(script):
        ch = script[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < len(script):
                out.append(script[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
        elif ch == '"':
            flush()
            out.append(ch)
            in_string = True
        elif ch == "#":
            flush()
            end = script.find("\n", i)
            end = len(script) if end < 0 else end
            out.append(script[i:end])
            i = end
            continue
        else:
            buf.append(ch)
        i += 1
    flush()
    return "".join(out)


def default_points(width: int = 1920, height: int = 1080) -> list[Point]:
    """Пара точек по умолчанию — чтобы новый пресет не был пустым."""
    return [
        Point(name="Точка1", x=width // 2, y=height // 2, color="#5B8CFF"),
        Point(name="Точка2", x=width // 2 + 120, y=height // 2 + 80, color="#4ED6A1"),
    ]
