"""Async in-proc pub/sub for SSE streaming."""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, AsyncIterator


@dataclass
class Event:
    type: str
    run_id: str
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self))


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()

    async def publish(self, event: Event) -> None:
        for q in list(self._subscribers):
            await q.put(event)

    def subscribe(self) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=128)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        self._subscribers.discard(q)

    async def stream(self) -> AsyncIterator[Event]:
        q = self.subscribe()
        try:
            while True:
                event = await q.get()
                yield event
        finally:
            self.unsubscribe(q)
