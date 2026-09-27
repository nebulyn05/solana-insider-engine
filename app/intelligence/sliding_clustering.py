from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.database.connection import get_connection


@dataclass(frozen=True)
class SlidingCluster:
    token_mint: str
    window_start: datetime
    window_end: datetime
    warm_wallets: tuple[str, ...]
    event_count: int
    representative_price: Decimal


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def find_best_sliding_window_cluster(
    token_mint: str,
    since: datetime,
    until: datetime,
    min_warm_wallets: int = 3,
    window_seconds: int = 30,
) -> SlidingCluster | None:
    if not token_mint:
        raise ValueError("token_mint is required")
    if min_warm_wallets < 2:
        raise ValueError("min_warm_wallets must be at least 2")
    if window_seconds < 1:
        raise ValueError("window_seconds must be positive")
    start, end = _utc(since), _utc(until)
    if end < start:
        raise ValueError("until must be >= since")

    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """SELECT e.wallet_address,e.observed_at,e.executed_price
               FROM token_buy_events e
               JOIN tracked_wallets w
                 ON w.wallet_address=e.wallet_address
                AND w.network='mainnet-beta'
               WHERE e.token_mint=%s
                 AND e.observed_at BETWEEN %s AND %s
                 AND w.is_tracked=TRUE AND w.is_warm=TRUE
               ORDER BY e.observed_at ASC,e.id ASC""",
            (token_mint, start, end),
        )
        rows = cursor.fetchall()

    events = deque()
    best = None
    window = timedelta(seconds=window_seconds)

    for wallet, observed_at, price in rows:
        event = (wallet, _utc(observed_at), Decimal(price))
        events.append(event)
        while events and event[1] - events[0][1] > window:
            events.popleft()

        by_wallet = {}
        for w, when, p in events:
            by_wallet.setdefault(w, (when, p))

        if len(by_wallet) < min_warm_wallets:
            continue

        first = min(v[0] for v in by_wallet.values())
        last = max(v[0] for v in by_wallet.values())
        prices = [v[1] for v in by_wallet.values()]
        count = len(by_wallet)
        score = (count, -int((last-first).total_seconds()*1000))
        if best is None or score > (best[0], -int((best[2]-best[1]).total_seconds()*1000)):
            best = (count, first, last, tuple(sorted(by_wallet)), sum(prices, Decimal("0"))/Decimal(count))

    if best is None:
        return None
    count, first, last, wallets, price = best
    return SlidingCluster(token_mint, first, last, wallets, count, price)
