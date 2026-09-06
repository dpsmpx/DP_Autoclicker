"""Движок исполнения: отдельный поток, пауза, остановка, события для UI."""

from __future__ import annotations

import math
import queue
import threading
import time
from typing import Callable, Optional

from .backends import BackendError, InputBackend, create_backend
from .hotkeys import normalize
from .models import Failsafe, Preset
from .runtime import actions as act
from .runtime.events import EngineEvent
from .runtime.interpreter import Interpreter
from .runtime.randomizer import Randomizer
from .script import ast_nodes as ast
from .script.errors import RuntimeScriptError, ScriptError
from .script.parser import parse

#: шаг «нарезки» пауз, чтобы остановка срабатывала мгновенно
_TICK = 0.02
#: как часто сверять положение курсора (секунды)
_GUARD_PERIOD = 0.05


class EngineStopped(Exception):
    """Внутренний сигнал остановки потока."""


class ScriptEngine:
    """Выполняет алгоритм пресета в фоновом потоке.

    Интерфейс общается с движком через очередь событий — так не нужно
    беспокоиться о потокобезопасности виджетов.
    """

    def __init__(
        self,
        backend_factory: Optional[Callable[[bool, tuple[int, int]], InputBackend]] = None,
    ) -> None:
        self.events: "queue.Queue[EngineEvent]" = queue.Queue()
        self._backend_factory = backend_factory or (
            lambda dry, screen: create_backend(dry_run=dry, screen=screen)
        )
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._lock = threading.Lock()
        self._backend: Optional[InputBackend] = None
        self.failsafe = Failsafe()
        #: где курсор должен находиться по мнению алгоритма
        self._expected_pos: Optional[tuple[int, int]] = None
        self._guard_checked_at = 0.0
        #: последнее сочетание, отправленное самим алгоритмом, и когда
        self._sent_keys: tuple[str, float] = ("", 0.0)
        self.stats = {"actions": 0, "clicks": 0, "keys": 0, "started_at": 0.0}

    # ------------------------------------------------------------ состояние
    @property
    def is_running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive())

    @property
    def is_paused(self) -> bool:
        return self._pause.is_set()

    def emit(self, kind: str, message: str = "", **kwargs) -> None:
        self.events.put(EngineEvent(kind=kind, message=message, **kwargs))

    def drain(self, limit: int = 400) -> list[EngineEvent]:
        """Забирает накопленные события (вызывается таймером интерфейса)."""
        out: list[EngineEvent] = []
        for _ in range(limit):
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                break
        return out

    # -------------------------------------------------------------- запуск
    def start(
        self,
        preset: Preset,
        body: Optional[ast.Block] = None,
        screen_size: Optional[tuple[int, int]] = None,
        failsafe: Optional[Failsafe] = None,
    ) -> bool:
        """Запускает алгоритм. Возвращает False, если запуск невозможен."""
        with self._lock:
            if self.is_running:
                self.emit("warning", "Алгоритм уже выполняется")
                return False
            try:
                program = body if body is not None else parse(preset.script).body
            except ScriptError as exc:
                self.emit("error", f"Ошибка в алгоритме — {exc}", line=exc.line)
                return False
            if not program:
                self.emit("warning", "Алгоритм пуст — добавьте хотя бы одно действие")
                return False

            missing = sorted(ast.used_points(program) - {p.name for p in preset.points})
            if missing:
                self.emit("error", "Не найдены точки: " + ", ".join(missing))
                return False

            self._stop.clear()
            self._pause.clear()
            self.failsafe = failsafe or Failsafe()
            self._expected_pos = None
            self._guard_checked_at = 0.0
            self.stats = {"actions": 0, "clicks": 0, "keys": 0, "started_at": time.time()}
            self._thread = threading.Thread(
                target=self._run,
                args=(preset, program, screen_size),
                name="dp-autoclicker-engine",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop(self) -> None:
        self._stop.set()
        self._pause.clear()

    def pause(self, reason: str = "") -> None:
        if self.is_running and not self._pause.is_set():
            self._pause.set()
            self.emit("paused", f"Пауза — {reason}" if reason else "Пауза",
                      data={"reason": reason})

    def resume(self) -> None:
        if self._pause.is_set():
            # курсор мог остаться где угодно: слежение возобновится
            # после того, как алгоритм сам передвинет его в следующий раз
            self._expected_pos = None
            self._pause.clear()
            self.emit("resumed", "Продолжаем")

    def toggle_pause(self) -> None:
        self.resume() if self.is_paused else self.pause()

    def recently_sent(self, combo: str, window: float = 0.3) -> bool:
        """Не мы ли сами только что нажали это сочетание?

        Алгоритм может нажимать клавиши, и системный слушатель иногда видит
        их как обычный ввод. Без этой проверки скрипт с `клавиша f6` сам себя
        останавливал бы. Сравниваем именно сочетание, поэтому настоящее
        нажатие пользователя не теряется.
        """
        sent, at = self._sent_keys
        if not sent or not combo:
            return False
        return sent == normalize(combo) and (time.monotonic() - at) < window

    def join(self, timeout: float = 5.0) -> None:
        thread = self._thread
        if thread:
            thread.join(timeout)

    # --------------------------------------------------------------- поток
    def _run(
        self, preset: Preset, program: ast.Block, screen_size: Optional[tuple[int, int]]
    ) -> None:
        backend: Optional[InputBackend] = None
        reason = "finished"
        try:
            screen = screen_size or (1920, 1080)
            backend = self._backend_factory(preset.run.dry_run, screen)
            self._backend = backend
            real_screen = backend.screen_size()
            if real_screen and real_screen[0] > 0:
                screen = real_screen

            randomizer = Randomizer(preset.randomization, screen_size=screen)
            interpreter = Interpreter(
                program,
                points={p.name: p for p in preset.points},
                randomizer=randomizer,
                run=preset.run,
                screen_size=screen,
                cursor=backend.position(),
            )

            mode = "сухой прогон" if preset.run.dry_run else backend.name
            self.emit("started", f"Запуск «{preset.name}» ({mode})")
            self._countdown(preset.run.start_delay)

            for action in interpreter.run_program():
                self._raise_if_stopped()
                self._perform(action, backend)
        except EngineStopped:
            reason = "stopped"
        except RuntimeScriptError as exc:
            reason = "error"
            self.emit("error", str(exc), line=exc.line)
        except BackendError as exc:
            reason = "error"
            self.emit("error", str(exc))
        except Exception as exc:  # pragma: no cover - неожиданный сбой
            reason = "error"
            self.emit("error", f"Внутренняя ошибка: {exc!r}")
        finally:
            if backend is not None:
                try:
                    backend.close()
                except Exception:  # pragma: no cover
                    pass
            self._backend = None
            elapsed = time.time() - (self.stats["started_at"] or time.time())
            titles = {
                "finished": "Алгоритм выполнен",
                "stopped": "Остановлено",
                "error": "Остановлено из-за ошибки",
            }
            self.emit(
                reason if reason != "error" else "finished",
                f"{titles[reason]} · действий: {self.stats['actions']} · "
                f"время: {elapsed:.1f} с",
                data={"reason": reason, "elapsed": elapsed, **self.stats},
            )

    # --------------------------------------------------------- исполнение
    def _raise_if_stopped(self) -> None:
        if self._stop.is_set():
            raise EngineStopped

    # ------------------------------------------------- страховка от помех
    def _sync_cursor(self, backend: InputBackend) -> None:
        """Запоминает, где курсор оказался после нашего же перемещения.

        Читаем фактическую позицию, а не желаемую: система могла подвинуть
        курсор сама (край экрана, масштабирование), и это не вмешательство.
        """
        if not self.failsafe.watch_user_move:
            return
        try:
            self._expected_pos = backend.position()
        except Exception:  # pragma: no cover - драйвер не отвечает
            self._expected_pos = None

    def _guard_user_input(self, backend: Optional[InputBackend]) -> None:
        """Если курсор уехал не по нашей воле — пауза (или остановка)."""
        if backend is None or not self.failsafe.watch_user_move:
            return
        if self._expected_pos is None or self._pause.is_set():
            return
        now = time.monotonic()
        if now - self._guard_checked_at < _GUARD_PERIOD:
            return
        self._guard_checked_at = now
        try:
            actual = backend.position()
        except Exception:  # pragma: no cover - драйвер не отвечает
            return
        drift = math.dist(actual, self._expected_pos)
        if drift < self.failsafe.threshold:
            return
        # дальше следить бессмысленно: курсор теперь там, куда его увёл человек
        self._expected_pos = None
        self.emit(
            "warning",
            f"Курсор сдвинут вручную (на {drift:.0f} px) — вмешательство пользователя",
            data={"drift": drift},
        )
        if self.failsafe.stop_instead_of_pause:
            self.stop()
        else:
            self.pause("вы двигали мышью")

    def _sleep(self, seconds: float) -> None:
        """Пауза, которую можно прервать и поставить на паузу."""
        deadline = time.monotonic() + max(0.0, seconds)
        while True:
            self._raise_if_stopped()
            self._guard_user_input(self._backend)
            if self._pause.is_set():
                paused_at = time.monotonic()
                while self._pause.is_set():
                    self._raise_if_stopped()
                    time.sleep(_TICK)
                deadline += time.monotonic() - paused_at
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(remaining, _TICK))

    def _countdown(self, seconds: float) -> None:
        remaining = int(round(seconds))
        while remaining > 0:
            self.emit("countdown", f"Старт через {remaining}…", data={"left": remaining})
            self._sleep(1.0)
            remaining -= 1

    def _glide(self, backend: InputBackend, path: list[tuple[int, int]], duration: float) -> None:
        """Проводит курсор по траектории за отведённое время."""
        if not path:
            return
        if duration <= 0 or len(path) == 1:
            x, y = path[-1]
            backend.move(x, y)
            self._sync_cursor(backend)
            return
        step = duration / len(path)
        for x, y in path:
            self._raise_if_stopped()
            backend.move(x, y)
            self._sync_cursor(backend)
            self._sleep(step)

    def _perform(self, action: act.Action, backend: InputBackend) -> None:
        if isinstance(action, act.Sleep):
            self._sleep(action.seconds)
            return
        if isinstance(action, act.LogMessage):
            self.emit("log", action.message, uid=action.uid, line=action.line)
            return

        # перед любым вводом убеждаемся, что мышь всё ещё «наша»,
        # и дожидаемся снятия паузы
        self._guard_user_input(backend)
        self._sleep(0.0)

        if isinstance(action, act.MoveTo):
            self._glide(backend, action.path or [(action.x, action.y)], action.duration)
        elif isinstance(action, act.ClickAt):
            self._glide(backend, action.path or [(action.x, action.y)], action.duration)
            backend.mouse_down(action.button)
            if action.hold > 0:
                self._sleep(action.hold)
            backend.mouse_up(action.button)
            self.stats["clicks"] += 1
        elif isinstance(action, act.MouseDown):
            if action.x is not None and action.y is not None:
                backend.move(action.x, action.y)
                self._sync_cursor(backend)
            backend.mouse_down(action.button)
        elif isinstance(action, act.MouseUp):
            backend.mouse_up(action.button)
        elif isinstance(action, act.ScrollBy):
            backend.scroll(action.dx, action.dy)
        elif isinstance(action, act.KeyTap):
            # запоминаем до отправки: слушатель может сработать мгновенно
            self._sent_keys = (normalize(action.combo), time.monotonic())
            backend.key_tap(action.combo)
            self.stats["keys"] += 1
        elif isinstance(action, act.TypeText):
            backend.type_text(action.text)
            self.stats["keys"] += len(action.text)
        else:  # pragma: no cover - защита от расширения набора действий
            raise RuntimeScriptError(f"Неизвестное действие {type(action).__name__}")

        self.stats["actions"] += 1
        self.emit(
            "action", action.title, uid=action.uid, line=action.line,
            data={"count": self.stats["actions"]},
        )
