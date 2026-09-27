from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.database.connection import get_connection
from app.execution.lifecycle import close_trade
from app.market.jupiter import quote_sell_to_sol


@dataclass(frozen=True)
class PositionPolicy:
    take_profit_pct: Decimal = Decimal("10")
    stop_loss_pct: Decimal = Decimal("8")
    max_hold_seconds: int = 900

    def validate(self) -> None:
        if self.take_profit_pct <= 0:
            raise ValueError("take_profit_pct must be positive")
        if self.stop_loss_pct <= 0:
            raise ValueError("stop_loss_pct must be positive")
        if self.max_hold_seconds < 1:
            raise ValueError("max_hold_seconds must be positive")


def _quote_price(token_mint: str, quantity: Decimal, decimals: int) -> Decimal | None:
    raw_amount = int(quantity * (Decimal(10) ** decimals))
    sol_value = quote_sell_to_sol(token_mint, raw_amount)
    if sol_value is None or quantity <= 0:
        return None
    return sol_value / quantity


def _evidence_decimals(value: Any) -> int | None:
    if isinstance(value, dict):
        parsed = value.get("output_decimals")
        return int(parsed) if parsed is not None else None
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return _evidence_decimals(parsed)
        except json.JSONDecodeError:
            return None
    return None


def manage_open_positions(policy: PositionPolicy = PositionPolicy()) -> int:
    """Manage paper positions using a current mainnet swap quote.

    The quote is read-only. No signing or transaction submission occurs.
    If the quote provider is unavailable, the latest observed buy mark is used
    as a simulation fallback.
    """
    policy.validate()
    now = datetime.now(timezone.utc)
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """SELECT trade_id, token_mint, quantity, executed_price, entry_at
               FROM simulated_trades
               WHERE side='BUY' AND status='OPEN'
                 AND metadata->>'detector' IN (
                     'phase5_48h_simulation',
                     'live_mainnet_pipeline',
                     'spatiotemporal_clustering'
                 )"""
        )
        positions = cursor.fetchall()

    closed = 0
    for trade_id, token_mint, quantity, entry_price, entry_at in positions:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT decimals FROM token_metadata WHERE mint_address=%s",
                (token_mint,),
            )
            row = cursor.fetchone()
            decimals = int(row[0]) if row else 0

            cursor.execute(
                """SELECT executed_price, detection_evidence
                   FROM token_buy_events
                   WHERE token_mint=%s AND observed_at >= %s
                   ORDER BY observed_at DESC, id DESC
                   LIMIT 1""",
                (token_mint, entry_at),
            )
            mark = cursor.fetchone()

        if mark is not None:
            evidence_decimals = _evidence_decimals(mark[1])
            if evidence_decimals is not None:
                decimals = evidence_decimals

        price = _quote_price(token_mint, Decimal(quantity), decimals)
        if price is None and mark is not None:
            price = Decimal(mark[0])
        if price is None or price <= 0:
            continue

        change_pct = (
            (price - Decimal(entry_price))
            / Decimal(entry_price)
            * Decimal("100")
        )
        age = (now - entry_at.astimezone(timezone.utc)).total_seconds()

        if change_pct >= policy.take_profit_pct:
            close_trade(trade_id, price, "take_profit")
            closed += 1
        elif change_pct <= -policy.stop_loss_pct:
            close_trade(trade_id, price, "stop_loss")
            closed += 1
        elif age >= policy.max_hold_seconds:
            close_trade(trade_id, price, "time_expiry", outcome="EXPIRED")
            closed += 1

    return closed
