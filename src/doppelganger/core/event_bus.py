"""
Doppelganger Event Bus
Central nervous system — all layers communicate through here.
Zero coupling between modules; everything is pub/sub.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class EventPriority(Enum):
    CRITICAL = auto()   # voice commands, safety triggers
    HIGH     = auto()   # perception events
    NORMAL   = auto()   # reasoning outputs, memory writes
    LOW      = auto()   # telemetry, logging


@dataclass
class Event:
    topic: str
    payload: Any
    source: str = "unknown"
    priority: EventPriority = EventPriority.NORMAL
    ts: float = field(default_factory=time.time)
    correlation_id: str | None = None

    def __repr__(self) -> str:
        return f"Event(topic={self.topic!r}, source={self.source!r}, ts={self.ts:.3f})"


# Type alias for async handler
Handler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """
    Async pub/sub event bus with priority queuing and topic wildcards.

    Topics follow dot-notation: 'perception.voice.transcript'
    Wildcards: 'perception.*' matches any sub-topic under perception.
    """

    def __init__(self, max_queue_size: int = 1024) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_queue_size)
        self._running = False
        self._task: asyncio.Task | None = None
        self._stats: dict[str, int] = defaultdict(int)

    # ─── Subscription ────────────────────────────────────────────────────────

    def subscribe(self, topic: str, handler: Handler) -> None:
        """Subscribe to exact topic or wildcard (e.g. 'perception.*')."""
        self._handlers[topic].append(handler)
        logger.debug("Subscribed %s → %s", handler.__qualname__, topic)

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        handlers = self._handlers.get(topic, [])
        if handler in handlers:
            handlers.remove(handler)

    # ─── Publishing ──────────────────────────────────────────────────────────

    async def publish(self, event: Event) -> None:
        priority_val = event.priority.value
        await self._queue.put((priority_val, time.time(), event))
        self._stats["published"] += 1

    async def publish_simple(
        self,
        topic: str,
        payload: Any,
        source: str = "unknown",
        priority: EventPriority = EventPriority.NORMAL,
    ) -> None:
        await self.publish(Event(topic=topic, payload=payload, source=source, priority=priority))

    # ─── Lifecycle ───────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._dispatch_loop(), name="event-bus-dispatch")
        logger.info("EventBus started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("EventBus stopped. Stats: %s", dict(self._stats))

    # ─── Internals ───────────────────────────────────────────────────────────

    async def _dispatch_loop(self) -> None:
        while self._running:
            try:
                _, _, event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                await self._dispatch(event)
                self._stats["dispatched"] += 1
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Dispatch error: %s", exc)
                self._stats["errors"] += 1

    async def _dispatch(self, event: Event) -> None:
        matched: list[Handler] = []

        # Exact match
        matched.extend(self._handlers.get(event.topic, []))

        # Wildcard match — 'perception.*' matches 'perception.voice.transcript'
        parts = event.topic.split(".")
        for depth in range(1, len(parts)):
            wildcard = ".".join(parts[:depth]) + ".*"
            matched.extend(self._handlers.get(wildcard, []))

        # Global catch-all
        matched.extend(self._handlers.get("*", []))

        if not matched:
            return

        tasks = [asyncio.create_task(h(event)) for h in matched]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                logger.error("Handler raised: %s", r)
                self._stats["handler_errors"] += 1

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)


# Global singleton — import this everywhere
bus = EventBus()
