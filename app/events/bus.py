from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

EventHandler = Callable[["EngineEvent"], Awaitable[None]]


@dataclass(frozen=True)
class EngineEvent:
    event_type: str
    occurred_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_type:
            raise ValueError("event_type is required")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")

    @property
    def utc_time(self) -> datetime:
        return self.occurred_at.astimezone(timezone.utc)


class AsyncEventBus:
    """In-process event bus used to decouple ingestion, scoring and simulation."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        if not event_type:
            raise ValueError("event_type is required")
        self._handlers.setdefault(event_type, []).append(handler)

    async def publish(self, event: EngineEvent) -> None:
        handlers = tuple(self._handlers.get(event.event_type, ()))
        if not handlers:
            return
        await asyncio.gather(*(handler(event) for handler in handlers))

    def handler_count(self, event_type: str) -> int:
        return len(self._handlers.get(event_type, ()))
