"""In-process event bus. The loop runs in a worker thread; the API streams events over SSE."""

from __future__ import annotations

import asyncio
import itertools
import threading
import time
from typing import Any

_counter = itertools.count(1)


class EventBus:
    def __init__(self, keep: int = 2000) -> None:
        self.keep = keep
        self.history: list[dict[str, Any]] = []
        self._subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self._lock = threading.Lock()

    def emit(self, type_: str, **data: Any) -> dict[str, Any]:
        event = {"id": next(_counter), "type": type_, "ts": time.time(), **data}
        with self._lock:
            self.history.append(event)
            del self.history[: -self.keep]
            subscribers = list(self._subscribers)
        for loop, queue in subscribers:
            loop.call_soon_threadsafe(queue.put_nowait, event)
        return event

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subscribers.append((asyncio.get_running_loop(), queue))
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers = [(lp, q) for lp, q in self._subscribers if q is not queue]

    def clear(self) -> None:
        with self._lock:
            self.history.clear()
