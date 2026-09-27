from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from app.database.connection import get_connection

DEFAULT_MIN_WARM_WALLETS = 3
DEFAULT_WINDOW_SECONDS = 30
DEFAULT_PAPER_NOTIONAL_SOL = Decimal("1")


@dataclass(frozen=True)
class BuyEvent:
    id: int
    wallet_address: str
    token_mint: str
    observed_at: datetime
    executed_price: Decimal
    transaction_signature: str


@dataclass(frozen=True)
class ClusterSignal:
    signal_id: str
    token_mint: str
    window_start: datetime
    window_end: datetime
    warm_wallets: tuple[str, ...]
    event_count: int
    representative_price: Decimal


@dataclass(frozen=True)
class PaperTradeTrigger:
    signal: ClusterSignal
    trade_id: UUID
    quantity: Decimal
    requested_price: Decimal
    executed_price: Decimal


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _validate_window(window_seconds: int) -> None:
    if window_seconds < 1:
        raise ValueError("window_seconds must be positive")


def _validate_threshold(min_warm_wallets: int) -> None:
    if min_warm_wallets < 2:
        raise ValueError("min_warm_wallets must be at least 2")


def record_buy_event(
    wallet_address: str,
    token_mint: str,
    transaction_signature: str,
    observed_at: datetime,
    executed_price: Decimal,
) -> int:
    """Persist a normalized observed BUY event.

    This is an observation record only; it never submits a blockchain
    transaction.
    """
    if not all((wallet_address, token_mint, transaction_signature)):
        raise ValueError("wallet, token mint, and signature are required")
    if executed_price < 0:
        raise ValueError("executed_price must not be negative")

    observed_at = _utc(observed_at)
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """INSERT INTO token_buy_events
               (wallet_address, token_mint, transaction_signature,
                observed_at, executed_price)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (transaction_signature) DO NOTHING
               RETURNING id""",
            (
                wallet_address,
                token_mint,
                transaction_signature,
                observed_at,
                executed_price,
            ),
        )
        row = cursor.fetchone()
        conn.commit()
        return int(row[0]) if row else 0


def find_spatiotemporal_cluster(
    token_mint: str,
    anchor_time: datetime,
    min_warm_wallets: int = DEFAULT_MIN_WARM_WALLETS,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
) -> ClusterSignal | None:
    """Find a qualifying warm-wallet buy cluster around an anchor event.

    The cluster condition is:
        |W_token,t| >= X
    where W_token,t is the set of distinct listed warm wallets that bought
    the exact token during [anchor_time-window, anchor_time+window].

    A wallet contributes at most once to X, preventing one wallet from
    satisfying the threshold by issuing multiple buys.
    """
    if not token_mint:
        raise ValueError("token_mint is required")
    _validate_threshold(min_warm_wallets)
    _validate_window(window_seconds)

    anchor_time = _utc(anchor_time)
    window = timedelta(seconds=window_seconds)
    start = anchor_time - window
    end = anchor_time + window

    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """SELECT DISTINCT ON (e.wallet_address)
                       e.id,
                       e.wallet_address,
                       e.token_mint,
                       e.observed_at,
                       e.executed_price,
                       e.transaction_signature
               FROM token_buy_events e
               JOIN tracked_wallets w
                 ON w.wallet_address = e.wallet_address
                AND w.network = 'devnet'
               WHERE e.token_mint = %s
                 AND e.observed_at BETWEEN %s AND %s
                 AND w.is_tracked = TRUE
                 AND (
                     w.is_warm = TRUE
                     OR LOWER(COALESCE(w.label, '')) = 'warm'
                     OR LOWER(COALESCE(w.metadata->>'temperature', '')) = 'warm'
                 )
               ORDER BY e.wallet_address, e.observed_at ASC""",
            (token_mint, start, end),
        )
        rows = cursor.fetchall()

    if len(rows) < min_warm_wallets:
        return None

    events = [
        BuyEvent(
            id=int(row[0]),
            wallet_address=row[1],
            token_mint=row[2],
            observed_at=_utc(row[3]),
            executed_price=Decimal(row[4]),
            transaction_signature=row[5],
        )
        for row in rows
    ]
    cluster_start = max(start, min(event.observed_at for event in events))
    cluster_end = min(end, max(event.observed_at for event in events))
    prices = [event.executed_price for event in events]
    representative_price = sum(prices, Decimal(0)) / Decimal(len(prices))

    signal_id = (
        f"cluster:{token_mint}:{cluster_start.isoformat()}:"
        f"{cluster_end.isoformat()}"
    )

    return ClusterSignal(
        signal_id=signal_id,
        token_mint=token_mint,
        window_start=cluster_start,
        window_end=cluster_end,
        warm_wallets=tuple(sorted(event.wallet_address for event in events)),
        event_count=len(events),
        representative_price=representative_price,
    )


def trigger_paper_trade(
    signal: ClusterSignal,
    notional_sol: Decimal = DEFAULT_PAPER_NOTIONAL_SOL,
) -> PaperTradeTrigger:
    """Create an OPEN simulated BUY from a qualifying cluster signal."""
    if notional_sol <= 0:
        raise ValueError("notional_sol must be positive")
    if signal.representative_price <= 0:
        raise ValueError("cluster representative price must be positive")

    quantity = notional_sol / signal.representative_price
    trade_id = uuid4()

    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """INSERT INTO token_metadata (mint_address, network)
               VALUES (%s, 'devnet')
               ON CONFLICT (mint_address) DO NOTHING""",
            (signal.token_mint,),
        )
        cursor.execute(
            """SELECT id
               FROM tracked_wallets
               WHERE wallet_address = %s
               LIMIT 1""",
            (signal.warm_wallets[0],),
        )
        wallet_row = cursor.fetchone()
        wallet_id = wallet_row[0] if wallet_row else None

        cursor.execute(
            """INSERT INTO simulated_trades
               (trade_id, wallet_id, token_mint, side, status, quantity,
                requested_price, executed_price, requested_notional,
                executed_notional, signal_id, metadata)
               VALUES (%s, %s, %s, 'BUY', 'OPEN', %s, %s, %s, %s, %s, %s, %s::jsonb)
               ON CONFLICT (signal_id) DO NOTHING
               RETURNING trade_id""",
            (
                str(trade_id),
                wallet_id,
                signal.token_mint,
                quantity,
                signal.representative_price,
                signal.representative_price,
                notional_sol,
                notional_sol,
                signal.signal_id,
                '{"detector":"spatiotemporal_clustering","execution":"paper"}',
            ),
        )
        row = cursor.fetchone()
        conn.commit()

    if row is None:
        raise ValueError(f"paper trade already exists for signal {signal.signal_id}")

    return PaperTradeTrigger(
        signal=signal,
        trade_id=UUID(str(row[0])),
        quantity=quantity,
        requested_price=signal.representative_price,
        executed_price=signal.representative_price,
    )


def evaluate_and_paper_trade(
    token_mint: str,
    anchor_time: datetime,
    min_warm_wallets: int = DEFAULT_MIN_WARM_WALLETS,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
    notional_sol: Decimal = DEFAULT_PAPER_NOTIONAL_SOL,
) -> PaperTradeTrigger | None:
    signal = find_spatiotemporal_cluster(
        token_mint=token_mint,
        anchor_time=anchor_time,
        min_warm_wallets=min_warm_wallets,
        window_seconds=window_seconds,
    )
    if signal is None:
        return None
    return trigger_paper_trade(signal, notional_sol=notional_sol)
