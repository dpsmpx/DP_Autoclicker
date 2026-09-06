"""Интерпретатор DPScript.

Реализован генератором: каждое действие «выдаётся» наружу, а движок решает,
когда его выполнить, когда поставить на паузу и когда прервать. Благодаря
этому логика алгоритма полностью тестируется без реального ввода и без GUI.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Iterator, Optional

from ..models import Point, RunSettings
from ..script import ast_nodes as ast
from ..script.errors import RuntimeScriptError
from . import actions as act
from .randomizer import Randomizer

#: предохранитель от «пустого» бесконечного цикла
_EMPTY_LOOP_LIMIT = 3


class BreakSignal(Exception):
    """Внутренний сигнал `прервать`."""


class StopSignal(Exception):
    """Внутренний сигнал `стоп`."""


class Interpreter:
    def __init__(
        self,
        body: ast.Block,
        points: Optional[dict[str, Point]] = None,
        randomizer: Optional[Randomizer] = None,
        run: Optional[RunSettings] = None,
        screen_size: Optional[tuple[int, int]] = None,
        cursor: tuple[int, int] = (0, 0),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.body = body
        self.points = points or {}
        self.random = randomizer or Randomizer()
        self.run = run or RunSettings()
        self.screen_size = screen_size
        self.cursor = cursor
        self.clock = clock
        self.variables: dict[str, Any] = {}
        self.action_count = 0
        self.started_at = 0.0
        #: стек счётчиков итераций (для встроенной переменной `итерация`)
        self._loops: list[int] = []

    # ------------------------------------------------------------ публичное
    def run_program(self) -> Iterator[act.Action]:
        """Главный генератор: выдаёт действия по одному."""
        self.started_at = self.clock()
        self.action_count = 0
        self.random.reset()
        try:
            yield from self._exec_block(self.body)
        except StopSignal:
            return
        except BreakSignal:
            return

    # ------------------------------------------------------------ утилиты
    def _emit(self, action: act.Action, node: ast.Node) -> act.Action:
        action.uid = node.uid
        action.line = node.line
        if not isinstance(action, (act.Sleep, act.LogMessage)):
            self.action_count += 1
        return action

    def _scaled(self, seconds: float) -> float:
        return max(0.0, seconds / max(0.05, self.run.speed))

    def _resolve_point(self, name: str, node: ast.Node) -> Point:
        point = self.points.get(name)
        if point is None:
            raise RuntimeScriptError(
                f"Точка «{name}» не найдена. Добавьте её на вкладке «Точки»", node.line
            )
        return point

    def _target_position(self, target: Optional[ast.Target], node: ast.Node) -> tuple[int, int]:
        if target is None:
            return self.cursor
        if target.is_point:
            point = self._resolve_point(target.point, node)
            return self.random.position(point.x, point.y, point)
        x = int(round(self._number(self.eval(target.x), node, "координата X")))
        y = int(round(self._number(self.eval(target.y), node, "координата Y")))
        return self.random.position(x, y, None, key=f"@{x},{y}")

    @staticmethod
    def _number(value: Any, node: ast.Node, what: str = "значение") -> float:
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, (int, float)):
            return float(value)
        raise RuntimeScriptError(f"Ожидалось число ({what}), получено «{value}»", node.line)

    def _duration(self, expr: Optional[ast.Expr], node: ast.Node, default: float = 0.0) -> float:
        if expr is None:
            return default
        return max(0.0, self._number(self.eval(expr), node, "длительность"))

    # ---------------------------------------------------------- исполнение
    def _exec_block(self, block: ast.Block) -> Iterator[act.Action]:
        for stmt in block:
            yield from self._exec(stmt)

    def _exec(self, stmt: ast.Stmt) -> Iterator[act.Action]:
        self._check_limits(stmt)
        handler = _HANDLERS.get(type(stmt))
        if handler is None:
            if isinstance(stmt, ast.Comment):
                return
            raise RuntimeScriptError(
                f"Не умею выполнять «{type(stmt).__name__}»", stmt.line
            )
        yield from handler(self, stmt)

    def _check_limits(self, node: ast.Node) -> None:
        if self.run.max_actions and self.action_count >= self.run.max_actions:
            raise StopSignal
        if self.run.max_runtime and (self.clock() - self.started_at) >= self.run.max_runtime:
            raise StopSignal

    def _idle(self, node: ast.Node) -> Iterator[act.Action]:
        pause = self.random.idle_pause()
        if pause > 0:
            yield self._emit(act.Sleep(seconds=self._scaled(pause)), node)

    def _goto(self, node: ast.Node, x: int, y: int) -> tuple[float, list[tuple[int, int]]]:
        duration = self.random.move_duration()
        path = self.random.move_path(self.cursor, (x, y))
        self.cursor = (x, y)
        return duration, path

    # ----- конкретные инструкции
    def _do_click(self, stmt: ast.Click) -> Iterator[act.Action]:
        times = 1
        if stmt.times is not None:
            times = int(round(self._number(self.eval(stmt.times), stmt, "количество кликов")))
            if times < 0:
                raise RuntimeScriptError("Количество кликов не может быть отрицательным", stmt.line)
        for index in range(times):
            x, y = self._target_position(stmt.target, stmt)
            duration, path = self._goto(stmt, x, y)
            hold = (
                self._duration(stmt.hold, stmt)
                if stmt.hold is not None
                else self.random.hold_time()
            )
            yield self._emit(
                act.ClickAt(
                    x=x, y=y, button=stmt.button,
                    hold=self._scaled(hold), duration=duration, path=path,
                ),
                stmt,
            )
            if index < times - 1:
                yield self._emit(act.Sleep(seconds=self._scaled(self.random.click_gap())), stmt)
        yield from self._idle(stmt)

    def _do_move(self, stmt: ast.Move) -> Iterator[act.Action]:
        x, y = self._target_position(stmt.target, stmt)
        duration = self._duration(stmt.duration, stmt, self.random.move_duration())
        path = self.random.move_path(
            self.cursor, (x, y), humanize=duration > 0 or None
        )
        self.cursor = (x, y)
        yield self._emit(act.MoveTo(x=x, y=y, duration=duration, path=path), stmt)

    def _do_drag(self, stmt: ast.Drag) -> Iterator[act.Action]:
        sx, sy = self._target_position(stmt.source, stmt)
        _, path_in = self._goto(stmt, sx, sy)
        yield self._emit(act.MoveTo(x=sx, y=sy, duration=0.0, path=path_in), stmt)
        yield self._emit(act.MouseDown(x=sx, y=sy, button=stmt.button), stmt)
        tx, ty = self._target_position(stmt.target, stmt)
        duration = self._duration(stmt.duration, stmt, max(0.2, self.random.move_duration()))
        path = self.random.move_path(self.cursor, (tx, ty), humanize=True)
        self.cursor = (tx, ty)
        yield self._emit(act.MoveTo(x=tx, y=ty, duration=self._scaled(duration), path=path), stmt)
        yield self._emit(act.MouseUp(button=stmt.button), stmt)
        yield from self._idle(stmt)

    def _do_press(self, stmt: ast.Press) -> Iterator[act.Action]:
        if stmt.target is not None:
            x, y = self._target_position(stmt.target, stmt)
            _, path = self._goto(stmt, x, y)
            yield self._emit(act.MoveTo(x=x, y=y, duration=0.0, path=path), stmt)
            yield self._emit(act.MouseDown(x=x, y=y, button=stmt.button), stmt)
        else:
            yield self._emit(act.MouseDown(button=stmt.button), stmt)

    def _do_release(self, stmt: ast.Release) -> Iterator[act.Action]:
        yield self._emit(act.MouseUp(button=stmt.button), stmt)

    def _do_scroll(self, stmt: ast.Scroll) -> Iterator[act.Action]:
        amount = int(round(self._number(self.eval(stmt.amount), stmt, "величина прокрутки")))
        if stmt.target is not None:
            x, y = self._target_position(stmt.target, stmt)
            _, path = self._goto(stmt, x, y)
            yield self._emit(act.MoveTo(x=x, y=y, duration=0.0, path=path), stmt)
        yield self._emit(act.ScrollBy(dy=amount), stmt)

    def _do_key(self, stmt: ast.Key) -> Iterator[act.Action]:
        yield self._emit(act.KeyTap(combo=stmt.combo), stmt)
        yield from self._idle(stmt)

    def _do_type(self, stmt: ast.TypeText) -> Iterator[act.Action]:
        yield self._emit(act.TypeText(text=stmt.text), stmt)

    def _do_wait(self, stmt: ast.Wait) -> Iterator[act.Action]:
        seconds = self._duration(stmt.duration, stmt)
        yield self._emit(act.Sleep(seconds=self._scaled(self.random.delay(seconds))), stmt)

    def _do_log(self, stmt: ast.Log) -> Iterator[act.Action]:
        yield self._emit(act.LogMessage(message=_to_text(self.eval(stmt.value))), stmt)

    def _do_set(self, stmt: ast.SetVar) -> Iterator[act.Action]:
        self.variables[stmt.name] = self.eval(stmt.value)
        return
        yield  # pragma: no cover - делает функцию генератором

    def _do_break(self, stmt: ast.Break) -> Iterator[act.Action]:
        raise BreakSignal
        yield  # pragma: no cover

    def _do_stop(self, stmt: ast.Stop) -> Iterator[act.Action]:
        raise StopSignal
        yield  # pragma: no cover

    def _do_repeat(self, stmt: ast.Repeat) -> Iterator[act.Action]:
        count = int(round(self._number(self.eval(stmt.count), stmt, "число повторов")))
        self._loops.append(0)
        try:
            for i in range(max(0, count)):
                self._loops[-1] = i + 1
                try:
                    yield from self._exec_block(stmt.body)
                except BreakSignal:
                    break
        finally:
            self._loops.pop()

    def _do_loop(self, stmt: ast.Loop) -> Iterator[act.Action]:
        yield from self._run_loop(stmt, stmt.body, condition=None)

    def _do_while(self, stmt: ast.While) -> Iterator[act.Action]:
        yield from self._run_loop(stmt, stmt.body, condition=stmt.condition)

    def _run_loop(
        self, stmt: ast.Stmt, body: ast.Block, condition: Optional[ast.Expr]
    ) -> Iterator[act.Action]:
        self._loops.append(0)
        empty_rounds = 0
        try:
            while True:
                if condition is not None and not _truthy(self.eval(condition)):
                    break
                self._loops[-1] += 1
                self._check_limits(stmt)
                before = self.action_count
                try:
                    yield from self._exec_block(body)
                except BreakSignal:
                    break
                if self.action_count == before:
                    empty_rounds += 1
                    if empty_rounds >= _EMPTY_LOOP_LIMIT:
                        raise RuntimeScriptError(
                            "Бесконечный цикл без действий — добавьте внутрь клик или паузу",
                            stmt.line,
                        )
                else:
                    empty_rounds = 0
        finally:
            self._loops.pop()

    def _do_if(self, stmt: ast.If) -> Iterator[act.Action]:
        if _truthy(self.eval(stmt.condition)):
            yield from self._exec_block(stmt.body)
        elif stmt.orelse:
            yield from self._exec_block(stmt.orelse)

    def _do_comment(self, stmt: ast.Comment) -> Iterator[act.Action]:
        return
        yield  # pragma: no cover

    # ---------------------------------------------------------- выражения
    def eval(self, node: Optional[ast.Expr]) -> Any:
        if node is None:
            return 0.0
        if isinstance(node, ast.Literal):
            return node.value
        if isinstance(node, ast.Var):
            return self._eval_var(node)
        if isinstance(node, ast.Range):
            low = self._number(self.eval(node.low), node, "начало диапазона")
            high = self._number(self.eval(node.high), node, "конец диапазона")
            return self.random.uniform(low, high)
        if isinstance(node, ast.Unary):
            if node.op == "not":
                return not _truthy(self.eval(node.operand))
            return -self._number(self.eval(node.operand), node)
        if isinstance(node, ast.Binary):
            return self._eval_binary(node)
        if isinstance(node, ast.Call):
            return self._eval_call(node)
        raise RuntimeScriptError(f"Неизвестное выражение {type(node).__name__}", node.line)

    def _eval_var(self, node: ast.Var) -> Any:
        name = node.name
        if name == "iteration":
            return float(self._loops[-1]) if self._loops else 0.0
        if name == "elapsed":
            return float(self.clock() - self.started_at)
        if name == "actions":
            return float(self.action_count)
        if name in self.variables:
            return self.variables[name]
        raise RuntimeScriptError(
            f"Переменная «{name}» не задана — присвойте ей значение через «пусть»", node.line
        )

    def _eval_binary(self, node: ast.Binary) -> Any:
        if node.op == "and":
            return _truthy(self.eval(node.left)) and _truthy(self.eval(node.right))
        if node.op == "or":
            return _truthy(self.eval(node.left)) or _truthy(self.eval(node.right))
        left = self.eval(node.left)
        right = self.eval(node.right)
        if node.op in ("==", "!="):
            equal = left == right
            return equal if node.op == "==" else not equal
        if node.op == "+" and (isinstance(left, str) or isinstance(right, str)):
            return _to_text(left) + _to_text(right)
        a = self._number(left, node)
        b = self._number(right, node)
        if node.op == "+":
            return a + b
        if node.op == "-":
            return a - b
        if node.op == "*":
            return a * b
        if node.op in ("/", "mod"):
            if b == 0:
                raise RuntimeScriptError("Деление на ноль", node.line)
            return a / b if node.op == "/" else a % b
        if node.op == "<":
            return a < b
        if node.op == "<=":
            return a <= b
        if node.op == ">":
            return a > b
        if node.op == ">=":
            return a >= b
        raise RuntimeScriptError(f"Неизвестная операция «{node.op}»", node.line)

    def _eval_call(self, node: ast.Call) -> Any:
        args = [self.eval(a) for a in node.args]

        def need(count: int) -> None:
            if len(args) != count:
                raise RuntimeScriptError(
                    f"Функция «{node.name}» ожидает {count} аргумент(ов), передано {len(args)}",
                    node.line,
                )

        if node.name == "chance":
            need(1)
            return self.random.chance(self._number(args[0], node, "вероятность"))
        if node.name == "random":
            need(2)
            return self.random.uniform(
                self._number(args[0], node), self._number(args[1], node)
            )
        if node.name == "min":
            need(2)
            return min(self._number(args[0], node), self._number(args[1], node))
        if node.name == "max":
            need(2)
            return max(self._number(args[0], node), self._number(args[1], node))
        if node.name == "round":
            need(1)
            return float(round(self._number(args[0], node)))
        if node.name == "abs":
            need(1)
            return abs(self._number(args[0], node))
        raise RuntimeScriptError(f"Неизвестная функция «{node.name}»", node.line)


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value)
    return bool(value)


def _to_text(value: Any) -> str:
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, float):
        if abs(value - round(value)) < 1e-9:
            return str(int(round(value)))
        return f"{value:g}"
    return str(value)


_HANDLERS: dict[type, Any] = {
    ast.Click: Interpreter._do_click,
    ast.Move: Interpreter._do_move,
    ast.Drag: Interpreter._do_drag,
    ast.Press: Interpreter._do_press,
    ast.Release: Interpreter._do_release,
    ast.Scroll: Interpreter._do_scroll,
    ast.Key: Interpreter._do_key,
    ast.TypeText: Interpreter._do_type,
    ast.Wait: Interpreter._do_wait,
    ast.Log: Interpreter._do_log,
    ast.SetVar: Interpreter._do_set,
    ast.Break: Interpreter._do_break,
    ast.Stop: Interpreter._do_stop,
    ast.Repeat: Interpreter._do_repeat,
    ast.Loop: Interpreter._do_loop,
    ast.While: Interpreter._do_while,
    ast.If: Interpreter._do_if,
    ast.Comment: Interpreter._do_comment,
}


def collect(
    body: ast.Block, points: Optional[dict[str, Point]] = None, limit: int = 10_000, **kwargs: Any
) -> list[act.Action]:
    """Выполняет алгоритм «на бумаге» и возвращает список действий.

    Используется тестами и режимом предпросмотра: реального ввода не происходит.
    """
    interp = Interpreter(body, points=points, **kwargs)
    out: list[act.Action] = []
    for action in interp.run_program():
        out.append(action)
        if len(out) >= limit:
            break
    return out
