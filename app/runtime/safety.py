from __future__ import annotations

import os

from app.config.settings import settings


FORBIDDEN_KEY_NAMES = (
    "SOLANA_PRIVATE_KEY",
    "PRIVATE_KEY",
    "WALLET_SECRET",
    "KEYPAIR_PATH",
)


def assert_paper_runtime() -> None:
    if settings.solana_network != "mainnet-beta":
        raise RuntimeError("live engine requires Solana mainnet-beta")
    if not settings.paper_trading:
        raise RuntimeError("live engine refuses PAPER_TRADING=false")
    if settings.live_execution:
        raise RuntimeError("live engine refuses LIVE_EXECUTION=true")

    # A live observer does not need a signing secret. Refuse common key
    # environment variables so accidental credential injection cannot turn
    # this process into an execution process.
    for name in FORBIDDEN_KEY_NAMES:
        if os.getenv(name):
            raise RuntimeError(
                f"{name} is not accepted by the paper-only runtime; remove signing credentials"
            )
