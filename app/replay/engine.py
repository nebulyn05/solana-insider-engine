from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, Iterable
from uuid import UUID, uuid4

from app.events.bus import EngineEvent


@dataclass(frozen=True)
class ReplayRecord:
    event_type: str
    event_at: datetime
    payload: dict

    def as_event(self) -> EngineEvent:
        return EngineEvent(self.event_type, self.event_at, self.payload)


class ReplayEngine:
    def __init__(self, records: Iterable[ReplayRecord]) -> None:
        self.records = tuple(sorted(records, key=lambda r: r.event_at))

    @classmethod
    def from_jsonl(cls, lines: Iterable[str]) -> "ReplayEngine":
        records = []
        for line in lines:
            if not line.strip():
                continue
            obj = json.loads(line)
            when = datetime.fromisoformat(obj["event_at"].replace("Z", "+00:00"))
            if when.tzinfo is None:
                raise ValueError("replay event_at must include timezone")
            records.append(ReplayRecord(obj["event_type"], when, obj.get("payload", {})))
        return cls(records)

    async def run(
        self,
        publish: Callable[[EngineEvent], Awaitable[None]],
        speed: float = 0,
    ) -> UUID:
        if speed < 0:
            raise ValueError("speed cannot be negative")
        run_id = uuid4()
        previous: datetime | None = None
        for record in self.records:
            if previous is not None and speed > 0:
                delay = (record.event_at - previous).total_seconds() / speed
                if delay > 0:
                    await asyncio.sleep(delay)
            await publish(record.as_event())
            previous = record.event_at
        return run_id
