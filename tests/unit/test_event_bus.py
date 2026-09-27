import asyncio
from datetime import datetime, timezone

from app.events.bus import AsyncEventBus, EngineEvent


def test_event_bus_dispatches_to_subscribers() -> None:
    async def run():
        bus = AsyncEventBus()
        seen = []

        async def handler(event):
            seen.append(event.payload["id"])

        bus.subscribe("BUY", handler)
        await bus.publish(EngineEvent("BUY", datetime.now(timezone.utc), {"id": 1}))
        assert seen == [1]

    asyncio.run(run())
