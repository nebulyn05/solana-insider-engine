from __future__ import annotations

import asyncio
import logging

from app.config.settings import settings
from app.ingestion.helius.laserstream import LaserStreamClient
from app.ingestion.normalizers.cex_outflow import (
    enrich_freshness,
    normalize_cex_outflow,
    persist_outflows,
)

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)


async def main() -> None:
    wallets = [
        item.strip()
        for item in (settings.helius_cex_wallets or "").split(",")
        if item.strip()
    ]
    if not wallets:
        raise RuntimeError(
            "HELIUS_CEX_WALLETS must contain at least one Devnet test hot-wallet address"
        )

    cex_wallets = set(wallets)
    client = LaserStreamClient(wallets)

    async for update in client.updates():
        candidates = normalize_cex_outflow(update, cex_wallets)
        fresh = await enrich_freshness(candidates)
        inserted = persist_outflows(fresh)
        if inserted:
            logger.info(
                "Persisted %d fresh CEX outflow(s) from slot %d",
                inserted,
                update.transaction.slot,
            )


if __name__ == "__main__":
    asyncio.run(main())
