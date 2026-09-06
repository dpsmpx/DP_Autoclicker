"""Словарь ключевых слов DPScript: русский и английский диалекты.

Язык намеренно двуязычный: пользователю не нужно учить английские слова,
а обмен пресетами не ломается, потому что парсер понимает оба варианта.
"""

from __future__ import annotations

#: канонический токен -> кортеж синонимов (первый — «эталон» диалекта)
RU_WORDS: dict[str, tuple[str, ...]] = {
    "click": ("клик", "кликнуть", "нажать"),
    "move": ("навести", "курсор"),
    "drag": ("перетащить", "тащить"),
    "press": ("зажать",),
    "release": ("отпустить",),
    "scroll": ("прокрутить", "прокрутка"),
    "key": ("клавиша", "клавиши"),
    "type": ("печатать", "ввести"),
    "wait": ("ждать", "пауза", "подождать"),
    "repeat": ("повторить", "повтор"),
    "loop": ("цикл", "бесконечно"),
    "while": ("пока",),
    "if": ("если",),
    "else": ("иначе",),
    "set": ("пусть", "задать"),
    "break": ("прервать",),
    "stop": ("стоп", "остановить"),
    "log": ("сообщение", "лог"),
    "to": ("к", "до"),
    "at": ("на",),
    "with": ("кнопкой",),
    "in": ("за",),
    "times": ("раз",),
    "hold": ("удерживая", "удержание"),
    "and": ("и",),
    "or": ("или",),
    "not": ("не",),
    "mod": ("остаток",),
    "true": ("да", "истина"),
    "false": ("нет", "ложь"),
    "left": ("левая", "лкм", "лев"),
    "right": ("правая", "пкм", "прав"),
    "middle": ("средняя", "скм", "сред"),
}

EN_WORDS: dict[str, tuple[str, ...]] = {canon: (canon,) for canon in RU_WORDS}
#: дополнительные английские синонимы
EN_WORDS["press"] = ("press", "down")
EN_WORDS["release"] = ("release", "up")
EN_WORDS["type"] = ("type", "write")
EN_WORDS["log"] = ("log", "say")

#: слово (в нижнем регистре) -> канонический токен
WORD_TO_CANON: dict[str, str] = {}
for _table in (EN_WORDS, RU_WORDS):
    for _canon, _words in _table.items():
        for _w in _words:
            WORD_TO_CANON[_w] = _canon

KEYWORDS = frozenset(WORD_TO_CANON)

#: канонические ключевые слова, с которых может начинаться инструкция
STATEMENT_KEYWORDS = frozenset(
    {
        "click", "move", "drag", "press", "release", "scroll", "key", "type",
        "wait", "repeat", "loop", "while", "if", "set", "break", "stop", "log",
    }
)

BUTTON_KEYWORDS = {"left": "left", "right": "right", "middle": "middle"}

#: встроенные функции: канон -> синонимы
FUNCTIONS: dict[str, tuple[str, ...]] = {
    "chance": ("chance", "шанс"),
    "random": ("random", "случайно", "случайное"),
    "min": ("min", "мин"),
    "max": ("max", "макс"),
    "round": ("round", "округлить"),
    "abs": ("abs", "модуль"),
}
FUNC_TO_CANON: dict[str, str] = {
    w: canon for canon, words in FUNCTIONS.items() for w in words
}

#: встроенные переменные: канон -> синонимы
BUILTIN_VARS: dict[str, tuple[str, ...]] = {
    "iteration": ("iteration", "итерация"),
    "elapsed": ("elapsed", "время"),
    "actions": ("actions", "действий"),
}
VAR_TO_CANON: dict[str, str] = {
    w: canon for canon, words in BUILTIN_VARS.items() for w in words
}

#: единицы времени: суффикс -> множитель в секундах
TIME_UNITS: dict[str, float] = {
    "ms": 0.001, "мс": 0.001,
    "s": 1.0, "sec": 1.0, "с": 1.0, "сек": 1.0,
    "m": 60.0, "min": 60.0, "м": 60.0, "мин": 60.0,
}


def word(canon: str, dialect: str = "ru") -> str:
    """Возвращает слово канонического токена на нужном диалекте."""
    table = RU_WORDS if dialect == "ru" else EN_WORDS
    return table.get(canon, (canon,))[0]


def func_word(canon: str, dialect: str = "ru") -> str:
    words = FUNCTIONS.get(canon, (canon,))
    return words[1] if dialect == "ru" and len(words) > 1 else words[0]


def var_word(canon: str, dialect: str = "ru") -> str:
    words = BUILTIN_VARS.get(canon, (canon,))
    return words[1] if dialect == "ru" and len(words) > 1 else words[0]


def time_unit(dialect: str = "ru") -> tuple[str, str]:
    """Суффиксы миллисекунд и секунд для выбранного диалекта."""
    return ("мс", "с") if dialect == "ru" else ("ms", "s")


def is_reserved(name: str) -> bool:
    """Занято ли имя языком (нельзя использовать как имя точки/переменной)."""
    low = name.lower()
    return low in WORD_TO_CANON or low in FUNC_TO_CANON or low in VAR_TO_CANON
