from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.database.connection import get_connection


VALID_OUTCOMES = {"WIN", "LOSS", "FALSE_POSITIVE", "EXPIRED", "NO_LIQUIDITY", "CANCELLED"}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _outcome(exit_price: Decimal, entry_price: Decimal) -> str:
    return "WIN" if exit_price > entry_price else "LOSS"


def close_trade(
    trade_id: UUID | str,
    exit_price: Decimal,
    exit_reason: str,
    fees: Decimal = Decimal("0"),
    outcome: str | None = None,
    exit_at: datetime | None = None,
) -> Decimal:
    """Close a paper position and atomically calculate realized P&L."""
    if exit_price <= 0:
        raise ValueError("exit_price must be positive")
    if fees < 0:
        raise ValueError("fees must be non-negative")
    if not exit_reason:
        raise ValueError("exit_reason is required")
    if outcome is not None and outcome not in VALID_OUTCOMES:
        raise ValueError(f"unsupported outcome: {outcome}")

    close_time = _utc(exit_at or datetime.now(timezone.utc))
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """SELECT quantity, executed_price, entry_at, signal_id, metadata
               FROM simulated_trades
               WHERE trade_id = %s AND side = 'BUY' AND status = 'OPEN'
               FOR UPDATE""",
            (str(trade_id),),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError("open BUY trade not found")

        quantity = Decimal(row[0])
        entry_price = Decimal(row[1])
        pnl = (exit_price - entry_price) * quantity - fees
        final_outcome = outcome or _outcome(exit_price, entry_price)

        metadata: dict[str, Any] = row[4] if isinstance(row[4], dict) else json.loads(row[4] or "{}")
        metadata = dict(metadata)
        metadata["closed_by"] = exit_reason

        cursor.execute(
            """UPDATE simulated_trades
               SET status='CLOSED',
                   exit_price=%s,
                   exit_at=%s,
                   fees=%s,
                   realized_pnl=%s,
                   outcome=%s,
                   exit_reason=%s,
                   metadata=%s::jsonb
               WHERE trade_id=%s""",
            (
                exit_price, close_time, fees, pnl, final_outcome,
                exit_reason, json.dumps(metadata), str(trade_id),
            ),
        )
        cursor.execute(
            """INSERT INTO execution_events
               (signal_id, trade_id, event_type, event_at, metadata)
               VALUES (%s, %s, 'EXIT', %s, %s::jsonb)""",
            (row[3], str(trade_id), close_time, json.dumps({
                "exit_reason": exit_reason,
                "outcome": final_outcome,
            })),
        )
        conn.commit()
        return pnl


def cancel_trade(trade_id: UUID | str, reason: str) -> None:
    if not reason:
        raise ValueError("reason is required")
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """UPDATE simulated_trades
               SET status='CANCELLED', outcome='CANCELLED', exit_reason=%s,
                   exit_at=NOW()
               WHERE trade_id=%s AND side='BUY' AND status='OPEN'""",
            (reason, str(trade_id)),
        )
        if cursor.rowcount != 1:
            raise ValueError("open BUY trade not found")
        conn.commit()
