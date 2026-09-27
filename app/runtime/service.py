from __future__ import annotations

import asyncio
import logging
import os

from app.ingestion.mainnet_wallet_stream import run_forever as run_wallet_stream
from app.intelligence.social_cooccurrence import SocialCoOccurrenceFilter
from app.simulation.position_manager import manage_open_positions

LOGGER = logging.getLogger("live.engine")


async def _position_monitor() -> None:
    interval = float(os.getenv("POSITION_MONITOR_INTERVAL_SEC", "2"))
    while True:
        try:
            closed = await asyncio.to_thread(manage_open_positions)
            if closed:
                LOGGER.info("PAPER_POSITIONS_CLOSED count=%s", closed)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("position monitor failed")
        await asyncio.sleep(interval)


async def _social_monitor() -> None:
    interval = float(os.getenv("SOCIAL_CONFIRMATION_INTERVAL_SEC", "15"))
    limit = int(os.getenv("SOCIAL_CONFIRMATION_BATCH", "100"))
    matcher = SocialCoOccurrenceFilter()
    while True:
        try:
            confirmations = await asyncio.to_thread(matcher.evaluate_pending, limit)
            if confirmations:
                LOGGER.info("SOCIAL_CONFIRMATIONS count=%s", len(confirmations))
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("social confirmation monitor failed")
        await asyncio.sleep(interval)


async def run_live_engine() -> None:
    tasks = [
        asyncio.create_task(run_wallet_stream(), name="mainnet-wallet-stream"),
        asyncio.create_task(_position_monitor(), name="paper-position-monitor"),
        asyncio.create_task(_social_monitor(), name="social-confirmation-monitor"),
    ]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    for task in done:
        exc = task.exception()
        if exc is not None:
            raise exc


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_live_engine())


if __name__ == "__main__":
    main()
