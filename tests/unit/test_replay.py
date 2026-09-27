import asyncio
from datetime import datetime, timezone

from app.events.bus import AsyncEventBus
from app.replay.engine import ReplayEngine, ReplayRecord


def test_replay_preserves_order() -> None:
    async def run():
        records = [
            ReplayRecord("A", datetime(2026, 1, 1, tzinfo=timezone.utc), {"n": 1}),
            ReplayRecord("A", datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc), {"n": 2}),
        ]
        engine = ReplayEngine(records)
        bus = AsyncEventBus()
        seen = []

        async def handler(event):
            seen.append(event.payload["n"])

        bus.subscribe("A", handler)
        await engine.run(bus.publish)
        assert seen == [1, 2]

    asyncio.run(run())
