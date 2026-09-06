"""Синтаксический анализатор DPScript: текст -> дерево инструкций."""

from __future__ import annotations

from . import ast_nodes as ast
from .errors import ParseError
from .keywords import BUTTON_KEYWORDS, FUNC_TO_CANON, VAR_TO_CANON
from .lexer import Token, tokenize

#: приоритет бинарных операторов (больше — сильнее связывает)
COMPARISONS = ("==", "!=", "<", "<=", ">", ">=")


class Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0
        #: комментарии, «проглоченные» при разборе текущей инструкции
        self.trivia: list[Token] = []

    # ------------------------------------------------------------- служебное
    def _raw(self, offset: int = 0) -> Token:
        idx = min(self.pos + offset, len(self.tokens) - 1)
        return self.tokens[idx]

    def peek(self, offset: int = 0) -> Token:
        """Заглянуть вперёд, не сдвигая позицию (комментарии прозрачны)."""
        idx = self.pos
        seen = 0
        while idx < len(self.tokens) - 1:
            if self.tokens[idx].type == "COMMENT":
                idx += 1
                continue
            if seen == offset:
                return self.tokens[idx]
            seen += 1
            idx += 1
        return self.tokens[-1]

    def advance(self) -> Token:
        while self.tokens[self.pos].type == "COMMENT":
            self.trivia.append(self.tokens[self.pos])
            self.pos += 1
        token = self.tokens[self.pos]
        if token.type != "EOF":
            self.pos += 1
        return token

    def expect_op(self, op: str, what: str) -> Token:
        token = self.peek()
        if not token.is_op(op):
            raise ParseError(
                f"Ожидался «{op}» {what}, найдено «{self._describe(token)}»",
                token.line,
                token.column,
            )
        return self.advance()

    @staticmethod
    def _describe(token: Token) -> str:
        if token.type == "EOF":
            return "конец файла"
        return token.text or str(token.value)

    def at_end(self) -> bool:
        return self.peek().type == "EOF"

    # ------------------------------------------------------------- программа
    def parse_program(self) -> ast.Program:
        body = self.parse_statements(stop_on_brace=False)
        token = self.peek()
        if token.type != "EOF":
            raise ParseError(
                f"Лишний фрагмент «{self._describe(token)}»", token.line, token.column
            )
        return ast.Program(body=body)

    def parse_statements(self, stop_on_brace: bool) -> ast.Block:
        body: ast.Block = []
        while True:
            raw = self._raw()
            if raw.type == "COMMENT":
                self.pos += 1
                if raw.own_line:
                    body.append(ast.Comment(text=str(raw.value), line=raw.line))
                elif body:
                    body[-1].comment = str(raw.value)
                continue
            token = self.peek()
            if token.type == "EOF":
                break
            if stop_on_brace and token.is_op("}"):
                break
            self.trivia.clear()
            stmt = self.parse_statement()
            body.append(stmt)
            # примечание в конце той же строки — оно могло быть проглочено
            # при заглядывании вперёд либо ещё ждать в потоке токенов
            notes = [t for t in self.trivia if not t.own_line]
            trailing = self._raw()
            if trailing.type == "COMMENT" and not trailing.own_line:
                notes.append(trailing)
                self.pos += 1
            if notes:
                stmt.comment = str(notes[0].value)
        return body

    def parse_block(self) -> ast.Block:
        self.expect_op("{", "перед телом блока")
        body = self.parse_statements(stop_on_brace=True)
        self.expect_op("}", "в конце блока")
        return body

    # ----------------------------------------------------------- инструкции
    def parse_statement(self) -> ast.Stmt:
        token = self.peek()
        if token.type != "KEYWORD":
            raise ParseError(
                f"Инструкция должна начинаться с команды, а не с «{self._describe(token)}»",
                token.line,
                token.column,
            )
        handler = getattr(self, f"_stmt_{token.value}", None)
        if handler is None:
            raise ParseError(
                f"«{token.text or token.value}» нельзя использовать как команду",
                token.line,
                token.column,
            )
        return handler()

    def _stmt_click(self) -> ast.Click:
        kw = self.advance()
        node = ast.Click(line=kw.line, target=self.parse_target())
        while True:
            token = self.peek()
            if token.is_kw("with"):
                self.advance()
                node.button = self.parse_button()
            elif token.is_kw("times"):
                self.advance()
                node.times = self.parse_expr()
            elif token.is_kw("hold"):
                self.advance()
                node.hold = self.parse_expr()
            else:
                break
        return node

    def _stmt_move(self) -> ast.Move:
        kw = self.advance()
        node = ast.Move(line=kw.line, target=self.parse_target())
        if self.peek().is_kw("in"):
            self.advance()
            node.duration = self.parse_expr()
        return node

    def _stmt_drag(self) -> ast.Drag:
        kw = self.advance()
        node = ast.Drag(line=kw.line, source=self.parse_target())
        token = self.peek()
        if token.is_kw("to") or token.is_op("->"):
            self.advance()
        else:
            raise ParseError(
                "После точки начала перетаскивания ожидалось «к» (to)", token.line, token.column
            )
        node.target = self.parse_target()
        while True:
            token = self.peek()
            if token.is_kw("in"):
                self.advance()
                node.duration = self.parse_expr()
            elif token.is_kw("with"):
                self.advance()
                node.button = self.parse_button()
            else:
                break
        return node

    def _stmt_press(self) -> ast.Press:
        kw = self.advance()
        node = ast.Press(line=kw.line)
        if self.peek().type == "KEYWORD" and self.peek().value in BUTTON_KEYWORDS:
            node.button = self.parse_button()
        if self.peek().is_kw("at"):
            self.advance()
            node.target = self.parse_target()
        return node

    def _stmt_release(self) -> ast.Release:
        kw = self.advance()
        node = ast.Release(line=kw.line)
        if self.peek().type == "KEYWORD" and self.peek().value in BUTTON_KEYWORDS:
            node.button = self.parse_button()
        return node

    def _stmt_scroll(self) -> ast.Scroll:
        kw = self.advance()
        node = ast.Scroll(line=kw.line, amount=self.parse_expr())
        if self.peek().is_kw("at"):
            self.advance()
            node.target = self.parse_target()
        return node

    def _stmt_key(self) -> ast.Key:
        kw = self.advance()
        token = self.peek()
        if token.type == "STRING":
            self.advance()
            return ast.Key(line=kw.line, combo=str(token.value).strip())
        parts: list[str] = []
        while True:
            token = self.peek()
            if token.type in ("IDENT", "KEYWORD"):
                self.advance()
                parts.append((token.text or str(token.value)).lower())
            elif token.type == "NUMBER" and not parts:
                self.advance()
                parts.append(token.text)
            else:
                break
            if self.peek().is_op("+"):
                self.advance()
                continue
            break
        if not parts:
            token = self.peek()
            raise ParseError(
                "После «клавиша» ожидалось сочетание, например ctrl+c", token.line, token.column
            )
        return ast.Key(line=kw.line, combo="+".join(parts))

    def _stmt_type(self) -> ast.TypeText:
        kw = self.advance()
        token = self.peek()
        if token.type != "STRING":
            raise ParseError(
                "После «печатать» ожидался текст в кавычках", token.line, token.column
            )
        self.advance()
        return ast.TypeText(line=kw.line, text=str(token.value))

    def _stmt_wait(self) -> ast.Wait:
        kw = self.advance()
        return ast.Wait(line=kw.line, duration=self.parse_expr())

    def _stmt_repeat(self) -> ast.Repeat:
        kw = self.advance()
        count = self.parse_expr()
        if self.peek().is_kw("times"):
            self.advance()
        return ast.Repeat(line=kw.line, count=count, body=self.parse_block())

    def _stmt_loop(self) -> ast.Loop:
        kw = self.advance()
        return ast.Loop(line=kw.line, body=self.parse_block())

    def _stmt_while(self) -> ast.While:
        kw = self.advance()
        condition = self.parse_expr()
        return ast.While(line=kw.line, condition=condition, body=self.parse_block())

    def _stmt_if(self) -> ast.If:
        kw = self.advance()
        condition = self.parse_expr()
        node = ast.If(line=kw.line, condition=condition, body=self.parse_block())
        if self.peek().is_kw("else"):
            self.advance()
            if self.peek().is_kw("if"):
                node.orelse = [self._stmt_if()]
            else:
                node.orelse = self.parse_block()
        return node

    def _stmt_set(self) -> ast.SetVar:
        kw = self.advance()
        token = self.peek()
        if token.type != "IDENT":
            raise ParseError(
                f"После «пусть» ожидалось имя переменной, найдено «{self._describe(token)}»",
                token.line,
                token.column,
            )
        self.advance()
        self.expect_op("=", "после имени переменной")
        return ast.SetVar(line=kw.line, name=str(token.value), value=self.parse_expr())

    def _stmt_break(self) -> ast.Break:
        kw = self.advance()
        return ast.Break(line=kw.line)

    def _stmt_stop(self) -> ast.Stop:
        kw = self.advance()
        return ast.Stop(line=kw.line)

    def _stmt_log(self) -> ast.Log:
        kw = self.advance()
        return ast.Log(line=kw.line, value=self.parse_expr())

    # ---------------------------------------------------------------- цели
    def parse_button(self) -> str:
        token = self.peek()
        if token.type == "KEYWORD" and token.value in BUTTON_KEYWORDS:
            self.advance()
            return BUTTON_KEYWORDS[str(token.value)]
        raise ParseError(
            f"Ожидалась кнопка мыши (левая/правая/средняя), найдено «{self._describe(token)}»",
            token.line,
            token.column,
        )

    def parse_target(self) -> ast.Target:
        token = self.peek()
        if token.is_op("@"):
            self.advance()
            self.expect_op("(", "перед координатами")
            x = self.parse_expr()
            self.expect_op(",", "между координатами")
            y = self.parse_expr()
            self.expect_op(")", "после координат")
            return ast.Target(line=token.line, x=x, y=y)
        if token.type == "IDENT":
            self.advance()
            return ast.Target(line=token.line, point=str(token.value))
        raise ParseError(
            f"Ожидалось имя точки или @(x, y), найдено «{self._describe(token)}»",
            token.line,
            token.column,
        )

    # ---------------------------------------------------------- выражения
    def parse_expr(self) -> ast.Expr:
        left = self.parse_or()
        if self.peek().is_op(".."):
            token = self.advance()
            right = self.parse_or()
            return ast.Range(line=token.line, low=left, high=right)
        return left

    def parse_or(self) -> ast.Expr:
        node = self.parse_and()
        while self.peek().is_kw("or"):
            token = self.advance()
            node = ast.Binary(line=token.line, op="or", left=node, right=self.parse_and())
        return node

    def parse_and(self) -> ast.Expr:
        node = self.parse_not()
        while self.peek().is_kw("and"):
            token = self.advance()
            node = ast.Binary(line=token.line, op="and", left=node, right=self.parse_not())
        return node

    def parse_not(self) -> ast.Expr:
        if self.peek().is_kw("not"):
            token = self.advance()
            return ast.Unary(line=token.line, op="not", operand=self.parse_not())
        return self.parse_comparison()

    def parse_comparison(self) -> ast.Expr:
        node = self.parse_additive()
        token = self.peek()
        if token.type == "OP" and token.value in COMPARISONS:
            self.advance()
            return ast.Binary(
                line=token.line, op=str(token.value), left=node, right=self.parse_additive()
            )
        return node

    def parse_additive(self) -> ast.Expr:
        node = self.parse_multiplicative()
        while True:
            token = self.peek()
            if token.is_op("+", "-"):
                self.advance()
                node = ast.Binary(
                    line=token.line,
                    op=str(token.value),
                    left=node,
                    right=self.parse_multiplicative(),
                )
            else:
                return node

    def parse_multiplicative(self) -> ast.Expr:
        node = self.parse_unary()
        while True:
            token = self.peek()
            if token.is_op("*", "/") or token.is_kw("mod"):
                self.advance()
                op = "mod" if token.type == "KEYWORD" else str(token.value)
                node = ast.Binary(line=token.line, op=op, left=node, right=self.parse_unary())
            else:
                return node

    def parse_unary(self) -> ast.Expr:
        token = self.peek()
        if token.is_op("-"):
            self.advance()
            return ast.Unary(line=token.line, op="-", operand=self.parse_unary())
        return self.parse_primary()

    def parse_primary(self) -> ast.Expr:
        token = self.peek()
        if token.type == "NUMBER":
            self.advance()
            return ast.Literal(line=token.line, value=float(token.value), kind="number")
        if token.type == "DURATION":
            self.advance()
            return ast.Literal(line=token.line, value=float(token.value), kind="duration")
        if token.type == "PERCENT":
            self.advance()
            return ast.Literal(line=token.line, value=float(token.value), kind="percent")
        if token.type == "STRING":
            self.advance()
            return ast.Literal(line=token.line, value=str(token.value), kind="string")
        if token.is_kw("true", "false"):
            self.advance()
            return ast.Literal(line=token.line, value=token.value == "true", kind="bool")
        if token.is_op("("):
            self.advance()
            node = self.parse_expr()
            self.expect_op(")", "после выражения в скобках")
            return node
        if token.type == "IDENT":
            self.advance()
            name = str(token.value)
            if self.peek().is_op("("):
                self.advance()
                args: list[ast.Expr] = []
                if not self.peek().is_op(")"):
                    args.append(self.parse_expr())
                    while self.peek().is_op(","):
                        self.advance()
                        args.append(self.parse_expr())
                self.expect_op(")", "после аргументов функции")
                canon = FUNC_TO_CANON.get(name.lower())
                if canon is None:
                    raise ParseError(
                        f"Неизвестная функция «{name}»", token.line, token.column
                    )
                return ast.Call(line=token.line, name=canon, args=args)
            return ast.Var(line=token.line, name=VAR_TO_CANON.get(name.lower(), name))
        raise ParseError(
            f"Ожидалось значение, найдено «{self._describe(token)}»", token.line, token.column
        )


def parse(source: str) -> ast.Program:
    """Разбирает исходный текст алгоритма."""
    return Parser(tokenize(source)).parse_program()


def parse_block(source: str) -> ast.Block:
    return parse(source).body


def parse_expression(source: str) -> ast.Expr:
    """Разбирает одно выражение (для полей визуального конструктора)."""
    parser = Parser(tokenize(source))
    node = parser.parse_expr()
    token = parser.peek()
    if token.type != "EOF":
        raise ParseError(
            f"Лишний фрагмент «{parser._describe(token)}» в выражении", token.line, token.column
        )
    return node
