"""Лексер, парсер и печать DPScript."""

from __future__ import annotations

import pytest

from dp_autoclicker.core.script import ast_nodes as ast
from dp_autoclicker.core.script.errors import LexError, ParseError
from dp_autoclicker.core.script.lexer import tokenize
from dp_autoclicker.core.script.parser import parse, parse_expression
from dp_autoclicker.core.script.printer import to_source

RU = """# заголовок
повторить 3 раз {
    клик Точка1 кнопкой пкм раз 2  # хвост
    ждать 100мс..300мс
    если шанс(30%) и не (x >= 2) {
        перетащить Точка1 к @(10, 20) за 500мс
    } иначе если да {
        прервать
    }
}
пусть x = (итерация + 1) * 2 - (3 - 1)
клавиша ctrl+shift+s
печатать "привет"
зажать правая на Точка2
отпустить правая
прокрутить -3 на Точка2
пока x < 10 {
    пусть x = x + 1
}
цикл {
    стоп
}
"""


def test_lexer_reads_durations_percents_and_comments():
    tokens = {t.type: t for t in tokenize('ждать 100мс 1.5с 30% "текст" # к')}
    assert tokens["DURATION"].value == pytest.approx(1.5)
    assert tokens["PERCENT"].value == pytest.approx(0.3)
    assert tokens["STRING"].value == "текст"
    assert tokens["COMMENT"].value == "к"


def test_lexer_reports_position_of_unknown_symbol():
    with pytest.raises(LexError) as info:
        tokenize("клик A\nклик $")
    assert info.value.line == 2


def test_lexer_rejects_unknown_unit():
    with pytest.raises(LexError):
        tokenize("ждать 10парсек")


def test_parser_builds_expected_tree():
    body = parse(RU).body
    kinds = [type(stmt).__name__ for stmt in body]
    assert kinds[:3] == ["Comment", "Repeat", "SetVar"]
    repeat = body[1]
    assert isinstance(repeat, ast.Repeat)
    click = repeat.body[0]
    assert isinstance(click, ast.Click)
    assert click.button == "right"
    assert click.comment == "хвост"
    assert ast.used_points(body) == {"Точка1", "Точка2"}


def test_english_and_russian_are_the_same_program():
    ru = parse("повторить 2 { клик A\n ждать 1с }").body
    en = parse("repeat 2 { click A\n wait 1s }").body
    assert to_source(ru) == to_source(en)


@pytest.mark.parametrize("dialect", ["ru", "en"])
def test_printer_roundtrip_is_stable(dialect):
    body = parse(RU).body
    printed = to_source(body, dialect)
    assert to_source(parse(printed).body, dialect) == printed


def test_printer_keeps_operator_precedence():
    body = parse("пусть x = 1 - (2 - 3) * (4 + 5)").body
    assert to_source(body) == "пусть x = 1 - (2 - 3) * (4 + 5)"


def test_parse_errors_point_at_the_line():
    with pytest.raises(ParseError) as info:
        parse("клик A\nповторить {\n}")
    assert info.value.line == 2

    with pytest.raises(ParseError):
        parse("клик")
    with pytest.raises(ParseError):
        parse("перетащить A B")
    with pytest.raises(ParseError):
        parse("пусть = 5")
    with pytest.raises(ParseError):
        parse("клик A кнопкой синяя")


def test_parse_expression_and_unknown_function():
    assert isinstance(parse_expression("шанс(30%)"), ast.Call)
    with pytest.raises(ParseError):
        parse_expression("выдумка(1)")
    with pytest.raises(ParseError):
        parse_expression("1 + ")


def test_locate_and_rename_helpers():
    body = parse("повторить 2 { клик A }").body
    inner = body[0].body[0]
    block, index = ast.locate(body, inner.uid)
    assert block[index] is inner
    assert ast.rename_point(body, "A", "Б") == 1
    assert ast.used_points(body) == {"Б"}
