from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from app.database.connection import get_connection
from app.execution.lifecycle import close_trade


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


def manage_open_positions(policy: PositionPolicy = PositionPolicy()) -> int:
    """Mark paper positions using the latest observed token-buy price.

    This is deliberately a simulation mark source. It does not claim to be a
    real sell quote and never submits a transaction.
    """
    policy.validate()
    now = datetime.now(timezone.utc)
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """SELECT trade_id, token_mint, executed_price, entry_at
               FROM simulated_trades
               WHERE side='BUY' AND status='OPEN'
                 AND metadata->>'detector'='phase5_48h_simulation'"""
        )
        positions = cursor.fetchall()

    closed = 0
    for trade_id, token_mint, entry_price, entry_at in positions:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """SELECT executed_price, observed_at
                   FROM token_buy_events
                   WHERE token_mint=%s AND observed_at >= %s
                   ORDER BY observed_at DESC, id DESC
                   LIMIT 1""",
                (token_mint, entry_at),
            )
            mark = cursor.fetchone()
        if mark is None:
            continue

        price = Decimal(mark[0])
        change_pct = (price - Decimal(entry_price)) / Decimal(entry_price) * Decimal("100")
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
