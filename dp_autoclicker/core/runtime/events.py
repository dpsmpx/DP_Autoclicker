"""События движка, которые интерфейс показывает пользователю."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

#: started | countdown | action | log | warning | error | paused | resumed
#: | finished | stopped | stats
EventKind = str

LEVELS = {
    "log": "info",
    "action": "action",
    "warning": "warn",
    "error": "error",
}


@dataclass
class EngineEvent:
    kind: EventKind
    message: str = ""
    uid: str = ""
    line: int = 0
    data: dict[str, Any] = field(default_factory=dict)
    at: float = field(default_factory=time.time)

    @property
    def level(self) -> str:
        return LEVELS.get(self.kind, "info")

    @property
    def clock(self) -> str:
        return time.strftime("%H:%M:%S", time.localtime(self.at))
