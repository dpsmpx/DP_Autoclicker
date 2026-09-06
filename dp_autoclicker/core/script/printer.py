"""Обратное преобразование: дерево инструкций -> текст DPScript.

Нужно для визуального конструктора: пользователь собирает алгоритм блоками,
а программа показывает эквивалентный код (и наоборот).
"""

from __future__ import annotations

from . import ast_nodes as ast
from .keywords import func_word, time_unit, var_word, word

INDENT = "    "

#: приоритеты операторов — по ним расставляются скобки
PREC = {
    "range": 0,
    "or": 1,
    "and": 2,
    "not": 3,
    "cmp": 4,
    "add": 5,
    "mul": 6,
    "neg": 7,
    "atom": 8,
}
_OP_PREC = {
    "or": PREC["or"],
    "and": PREC["and"],
    "==": PREC["cmp"], "!=": PREC["cmp"], "<": PREC["cmp"],
    "<=": PREC["cmp"], ">": PREC["cmp"], ">=": PREC["cmp"],
    "+": PREC["add"], "-": PREC["add"],
    "*": PREC["mul"], "/": PREC["mul"], "mod": PREC["mul"],
}


def format_number(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:g}"


def format_duration(seconds: float, dialect: str = "ru") -> str:
    ms_unit, s_unit = time_unit(dialect)
    if seconds < 1.0:
        return f"{format_number(seconds * 1000)}{ms_unit}"
    return f"{format_number(seconds)}{s_unit}"


def quote(text: str) -> str:
    escaped = (
        text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
    )
    return f'"{escaped}"'


class Printer:
    def __init__(self, dialect: str = "ru") -> None:
        self.dialect = dialect

    def kw(self, canon: str) -> str:
        return word(canon, self.dialect)

    # ---------------------------------------------------------- выражения
    def expr(self, node: ast.Expr | None, parent_prec: int = 0) -> str:
        if node is None:
            return ""
        if isinstance(node, ast.Literal):
            return self._literal(node)
        if isinstance(node, ast.Var):
            return var_word(node.name, self.dialect) if node.name in ("iteration", "elapsed", "actions") else node.name
        if isinstance(node, ast.Call):
            args = ", ".join(self.expr(a) for a in node.args)
            return f"{func_word(node.name, self.dialect)}({args})"
        if isinstance(node, ast.Range):
            text = f"{self.expr(node.low, PREC['or'])}..{self.expr(node.high, PREC['or'])}"
            return self._wrap(text, PREC["range"], parent_prec)
        if isinstance(node, ast.Unary):
            if node.op == "not":
                text = f"{self.kw('not')} {self.expr(node.operand, PREC['not'])}"
                return self._wrap(text, PREC["not"], parent_prec)
            text = f"-{self.expr(node.operand, PREC['neg'])}"
            return self._wrap(text, PREC["neg"], parent_prec)
        if isinstance(node, ast.Binary):
            prec = _OP_PREC.get(node.op, PREC["add"])
            op = self.kw(node.op) if node.op in ("and", "or", "mod") else node.op
            left = self.expr(node.left, prec)
            right = self.expr(node.right, prec + 1)
            return self._wrap(f"{left} {op} {right}", prec, parent_prec)
        raise TypeError(f"Неизвестный узел выражения: {type(node).__name__}")

    @staticmethod
    def _wrap(text: str, prec: int, parent_prec: int) -> str:
        return f"({text})" if prec < parent_prec else text

    def _literal(self, node: ast.Literal) -> str:
        if node.kind == "duration":
            return format_duration(float(node.value), self.dialect)
        if node.kind == "percent":
            return f"{format_number(float(node.value) * 100)}%"
        if node.kind == "string":
            return quote(str(node.value))
        if node.kind == "bool":
            return self.kw("true" if node.value else "false")
        return format_number(float(node.value))

    def target(self, node: ast.Target | None) -> str:
        if node is None:
            return "@(0, 0)"
        if node.is_point:
            return node.point
        return f"@({self.expr(node.x)}, {self.expr(node.y)})"

    # --------------------------------------------------------- инструкции
    def block(self, body: ast.Block, level: int = 0) -> list[str]:
        lines: list[str] = []
        for stmt in body:
            lines.extend(self.statement(stmt, level))
        return lines

    def statement(self, stmt: ast.Stmt, level: int = 0) -> list[str]:
        pad = INDENT * level
        note = f"  # {stmt.comment}" if stmt.comment else ""

        if isinstance(stmt, ast.Comment):
            return [f"{pad}# {stmt.text}".rstrip()]
        if isinstance(stmt, ast.Click):
            parts = [self.kw("click"), self.target(stmt.target)]
            if stmt.button != "left":
                parts += [self.kw("with"), self.kw(stmt.button)]
            if stmt.times is not None:
                parts += [self.kw("times"), self.expr(stmt.times, PREC["atom"])]
            if stmt.hold is not None:
                parts += [self.kw("hold"), self.expr(stmt.hold, PREC["atom"])]
            return [pad + " ".join(parts) + note]
        if isinstance(stmt, ast.Move):
            parts = [self.kw("move"), self.target(stmt.target)]
            if stmt.duration is not None:
                parts += [self.kw("in"), self.expr(stmt.duration, PREC["atom"])]
            return [pad + " ".join(parts) + note]
        if isinstance(stmt, ast.Drag):
            parts = [
                self.kw("drag"), self.target(stmt.source),
                self.kw("to"), self.target(stmt.target),
            ]
            if stmt.duration is not None:
                parts += [self.kw("in"), self.expr(stmt.duration, PREC["atom"])]
            if stmt.button != "left":
                parts += [self.kw("with"), self.kw(stmt.button)]
            return [pad + " ".join(parts) + note]
        if isinstance(stmt, ast.Press):
            parts = [self.kw("press")]
            if stmt.button != "left" or stmt.target is None:
                parts.append(self.kw(stmt.button))
            if stmt.target is not None:
                parts += [self.kw("at"), self.target(stmt.target)]
            return [pad + " ".join(parts) + note]
        if isinstance(stmt, ast.Release):
            return [pad + f"{self.kw('release')} {self.kw(stmt.button)}" + note]
        if isinstance(stmt, ast.Scroll):
            parts = [self.kw("scroll"), self.expr(stmt.amount, PREC["neg"])]
            if stmt.target is not None:
                parts += [self.kw("at"), self.target(stmt.target)]
            return [pad + " ".join(parts) + note]
        if isinstance(stmt, ast.Key):
            return [pad + f"{self.kw('key')} {stmt.combo}" + note]
        if isinstance(stmt, ast.TypeText):
            return [pad + f"{self.kw('type')} {quote(stmt.text)}" + note]
        if isinstance(stmt, ast.Wait):
            return [pad + f"{self.kw('wait')} {self.expr(stmt.duration)}" + note]
        if isinstance(stmt, ast.SetVar):
            return [pad + f"{self.kw('set')} {stmt.name} = {self.expr(stmt.value)}" + note]
        if isinstance(stmt, ast.Break):
            return [pad + self.kw("break") + note]
        if isinstance(stmt, ast.Stop):
            return [pad + self.kw("stop") + note]
        if isinstance(stmt, ast.Log):
            return [pad + f"{self.kw('log')} {self.expr(stmt.value)}" + note]
        if isinstance(stmt, ast.Repeat):
            head = f"{pad}{self.kw('repeat')} {self.expr(stmt.count, PREC['atom'])} {{{note}"
            return [head, *self.block(stmt.body, level + 1), pad + "}"]
        if isinstance(stmt, ast.Loop):
            return [f"{pad}{self.kw('loop')} {{{note}", *self.block(stmt.body, level + 1), pad + "}"]
        if isinstance(stmt, ast.While):
            head = f"{pad}{self.kw('while')} {self.expr(stmt.condition)} {{{note}"
            return [head, *self.block(stmt.body, level + 1), pad + "}"]
        if isinstance(stmt, ast.If):
            lines = [f"{pad}{self.kw('if')} {self.expr(stmt.condition)} {{{note}"]
            lines += self.block(stmt.body, level + 1)
            if stmt.orelse:
                # `иначе если` печатаем в одну строку, а не вложенным блоком
                if len(stmt.orelse) == 1 and isinstance(stmt.orelse[0], ast.If):
                    nested = self.statement(stmt.orelse[0], level)
                    lines.append(f"{pad}}} {self.kw('else')} {nested[0].lstrip()}")
                    lines.extend(nested[1:])
                    return lines
                lines.append(f"{pad}}} {self.kw('else')} {{")
                lines += self.block(stmt.orelse, level + 1)
            lines.append(pad + "}")
            return lines
        raise TypeError(f"Неизвестная инструкция: {type(stmt).__name__}")


def to_source(body: ast.Block, dialect: str = "ru") -> str:
    """Печатает блок инструкций в текст."""
    return "\n".join(Printer(dialect).block(body))


def stmt_to_source(stmt: ast.Stmt, dialect: str = "ru") -> str:
    """Одна инструкция одной строкой — для подписи блока в конструкторе."""
    lines = Printer(dialect).statement(stmt)
    return lines[0].strip()
