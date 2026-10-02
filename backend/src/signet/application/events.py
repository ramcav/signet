"""Async in-proc pub/sub for SSE streaming."""
from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, AsyncIterator


@dataclass
class Event:
    type: str
    run_id: str
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    id: int = 0

    def to_json(self) -> str:
        def encode(value):
            if isinstance(value, Decimal) and value.is_finite():
                return format(value, "f")
            raise TypeError(f"unsupported event value: {type(value).__name__}")
        return json.dumps(asdict(self), default=encode, allow_nan=False)


class EventBus:
    def __init__(self) -> None:
        self._history: deque[Event] = deque(maxlen=2048)
        self._condition = asyncio.Condition()
        self._next_id = 0

    async def publish(self, event: Event) -> None:
        async with self._condition:
            self._next_id += 1
            event.id = self._next_id
            self._history.append(event)
            self._condition.notify_all()

    async def stream(self, last_event_id: int | None = None) -> AsyncIterator[Event]:
        # Initial subscribers receive recent history, covering the connection /
        # POST ordering race. Browsers send Last-Event-ID when reconnecting.
        cursor = last_event_id or 0
        while True:
            async with self._condition:
                reset = None
                if cursor > self._next_id:
                    reset = Event(type="stream.reset", run_id="", data={"reason": "restart"})
                    cursor = 0
                elif self._history and last_event_id is not None and cursor < self._history[0].id - 1:
                    reset = Event(type="stream.reset", run_id="", data={"reason": "history_expired"})
                    cursor = self._history[0].id - 1
            if reset:
                yield reset
            async with self._condition:
                await self._condition.wait_for(lambda: self._next_id > cursor)
                batch = [event for event in self._history if event.id > cursor]
            for event in batch:
                cursor = event.id
                yield event
