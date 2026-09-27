from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import urllib.request

from app.database.connection import get_connection
from app.intelligence.clustering import find_spatiotemporal_cluster

LOGGER = logging.getLogger("phase5.live_simulation")


@dataclass(frozen=True)
class SimulationConfig:
    duration_hours: Decimal = Decimal("48")
    poll_seconds: int = 5
    slippage_percent: Decimal = Decimal("4.0")
    notional_sol: Decimal = Decimal("1")

    def validate(self) -> None:
        if self.duration_hours <= 0:
            raise ValueError("duration_hours must be positive")
        if self.poll_seconds < 1:
            raise ValueError("poll_seconds must be positive")
        if not Decimal("3") <= self.slippage_percent <= Decimal("5"):
            raise ValueError("slippage_percent must be between 3 and 5")
        if self.notional_sol <= 0:
            raise ValueError("notional_sol must be positive")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _verify_devnet(rpc_url: str) -> None:
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getGenesisHash",
        "params": [],
    }).encode()
    request = urllib.request.Request(
        rpc_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        body = json.load(response)
    if body.get("error") or not body.get("result"):
        raise RuntimeError(f"Devnet RPC verification failed: {body.get('error')}")
    LOGGER.info("verified Solana RPC endpoint: %s", rpc_url)


def _candidate_events(after: datetime) -> list[tuple[int, str, datetime]]:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, token_mint, observed_at
            FROM token_buy_events
            WHERE observed_at >= %s
            ORDER BY observed_at ASC, id ASC
            """,
            (after,),
        )
        return [
            (int(row[0]), row[1], row[2].astimezone(timezone.utc))
            for row in cursor.fetchall()
        ]


def _insert_simulated_entry(
    token_mint: str,
    signal_id: str,
    requested_price: Decimal,
    notional_sol: Decimal,
    slippage_percent: Decimal,
) -> bool:
    slippage_bps = slippage_percent * Decimal("100")
    executed_price = requested_price * (
        Decimal("1") + slippage_percent / Decimal("100")
    )
    quantity = notional_sol / executed_price
    slippage_amount = executed_price - requested_price
    trade_id = str(uuid4())

    metadata = json.dumps({
        "detector": "phase5_48h_simulation",
        "execution": "paper",
        "environment": "devnet",
        "mock_public_block_delay_penalty_percent": str(slippage_percent),
        "mock_slippage_model": "fixed_buy_price_penalty",
    })

    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO token_metadata (mint_address, network)
            VALUES (%s, 'devnet')
            ON CONFLICT (mint_address) DO NOTHING
            """,
            (token_mint,),
        )
        cursor.execute(
            """
            INSERT INTO simulated_trades
                (trade_id, token_mint, side, status, quantity,
                 requested_price, executed_price, requested_notional,
                 executed_notional, slippage_bps, slippage_amount,
                 signal_id, metadata)
            VALUES
                (%s, %s, 'BUY', 'OPEN', %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (signal_id) DO NOTHING
            RETURNING id
            """,
            (
                trade_id,
                token_mint,
                quantity,
                requested_price,
                executed_price,
                notional_sol,
                notional_sol,
                slippage_bps,
                slippage_amount * quantity,
                signal_id,
                metadata,
            ),
        )
        row = cursor.fetchone()
        conn.commit()

    if row is None:
        return False

    LOGGER.info(
        "PAPER ENTRY token=%s requested=%s executed=%s slippage=%s%% notional=%s signal=%s",
        token_mint,
        requested_price,
        executed_price,
        slippage_percent,
        notional_sol,
        signal_id,
    )
    return True


def run(config: SimulationConfig) -> None:
    config.validate()

    rpc_url = os.getenv("SOLANA_RPC_URL", "https://api.devnet.solana.com")
    if "devnet" not in rpc_url.lower():
        raise RuntimeError("Phase 5 live simulation requires a Devnet RPC endpoint")

    _verify_devnet(rpc_url)

    started_at = _utc_now()
    deadline = started_at + timedelta(hours=float(config.duration_hours))
    cursor_time = started_at

    LOGGER.info(
        "starting 48-hour paper simulation until %s; fixed mock slippage=%s%%",
        deadline.isoformat(),
        config.slippage_percent,
    )

    while _utc_now() < deadline:
        events = _candidate_events(cursor_time)
        for _, token_mint, observed_at in events:
            cursor_time = max(cursor_time, observed_at + timedelta(microseconds=1))
            signal = find_spatiotemporal_cluster(token_mint, observed_at)
            if signal is None:
                continue

            _insert_simulated_entry(
                token_mint=signal.token_mint,
                signal_id=f"phase5:{signal.signal_id}",
                requested_price=signal.representative_price,
                notional_sol=config.notional_sol,
                slippage_percent=config.slippage_percent,
            )

        remaining = (deadline - _utc_now()).total_seconds()
        if remaining > 0:
            time.sleep(min(config.poll_seconds, remaining))

    LOGGER.info("48-hour paper simulation window completed")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the 48-hour Devnet paper-trading simulation."
    )
    parser.add_argument("--hours", type=Decimal, default=Decimal("48"))
    parser.add_argument("--poll-seconds", type=int, default=5)
    parser.add_argument("--slippage-percent", type=Decimal, default=Decimal("4.0"))
    parser.add_argument("--notional-sol", type=Decimal, default=Decimal("1"))
    args = parser.parse_args()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    run(
        SimulationConfig(
            duration_hours=args.hours,
            poll_seconds=args.poll_seconds,
            slippage_percent=args.slippage_percent,
            notional_sol=args.notional_sol,
        )
    )


if __name__ == "__main__":
    main()
