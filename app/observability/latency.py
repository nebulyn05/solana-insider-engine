from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping
from uuid import UUID


@dataclass(frozen=True)
class LatencySample:
    signal_created_at: datetime
    detected_at: datetime
    entry_at: datetime
    execution_at: datetime

    def __post_init__(self) -> None:
        values = (
            self.signal_created_at,
            self.detected_at,
            self.entry_at,
            self.execution_at,
        )
        if any(v.tzinfo is None for v in values):
            raise ValueError("all timestamps must be timezone-aware")
        if tuple(sorted(values)) != values:
            raise ValueError("latency timestamps must be monotonic")

    @staticmethod
    def _ms(start: datetime, end: datetime) -> Decimal:
        return Decimal(str((end - start).total_seconds() * 1000))

    def as_dict(self) -> Mapping[str, Decimal]:
        return {
            "entry_latency_ms": self._ms(self.signal_created_at, self.detected_at),
            "decision_latency_ms": self._ms(self.detected_at, self.entry_at),
            "execution_latency_ms": self._ms(self.entry_at, self.execution_at),
            "total_latency_ms": self._ms(self.signal_created_at, self.execution_at),
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def latency_from_timestamps(
    signal_created_at: datetime,
    detected_at: datetime,
    entry_at: datetime,
    execution_at: datetime,
) -> LatencySample:
    return LatencySample(signal_created_at, detected_at, entry_at, execution_at)
