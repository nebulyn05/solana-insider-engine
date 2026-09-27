from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.events.bus import AsyncEventBus
from app.replay.engine import ReplayEngine


async def run(path: str, speed: float) -> None:
    with open(path, "r", encoding="utf-8") as handle:
        engine = ReplayEngine.from_jsonl(handle)

    bus = AsyncEventBus()

    async def printer(event):
        print(json.dumps({
            "event_type": event.event_type,
            "event_at": event.utc_time.isoformat(),
            "payload": event.payload,
        }, separators=(",", ":")))

    for event_type in {r.event_type for r in engine.records}:
        bus.subscribe(event_type, printer)

    run_id = await engine.run(bus.publish, speed=speed)
    print(f"replay_run_id={run_id}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay normalized engine events from JSONL.")
    parser.add_argument("path")
    parser.add_argument("--speed", type=float, default=0.0,
                        help="0=as fast as possible; otherwise simulated time multiplier")
    args = parser.parse_args()
    asyncio.run(run(args.path, args.speed))


if __name__ == "__main__":
    main()
