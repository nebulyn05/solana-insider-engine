from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.database.connection import get_connection


@dataclass(frozen=True)
class WalletFeatures:
    wallet_address: str
    observed_buy_count: int
    distinct_token_count: int
    avg_inter_buy_seconds: Decimal | None
    shared_funder_count: int
    deployer_lineage_hits: int
    social_confirmation_count: int
    successful_signal_count: int
    failed_signal_count: int
    win_rate: Decimal | None
    reputation_score: Decimal


def refresh_wallet_features(wallet_address: str) -> WalletFeatures:
    if not wallet_address:
        raise ValueError("wallet_address is required")
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """WITH buys AS (
                   SELECT observed_at,
                          LAG(observed_at) OVER (ORDER BY observed_at) AS prev_at,
                          token_mint,
                          social_confirmed
                   FROM token_buy_events
                   WHERE wallet_address=%s
               ),
               signals AS (
                   SELECT
                       COUNT(*) FILTER (WHERE status='CLOSED' AND realized_pnl > 0) AS wins,
                       COUNT(*) FILTER (WHERE status='CLOSED' AND realized_pnl IS NOT NULL) AS closed
                   FROM simulated_trades st
                   JOIN tracked_wallets tw ON tw.id=st.wallet_id
                   WHERE tw.wallet_address=%s
               )
               SELECT
                   COUNT(*),
                   COUNT(DISTINCT token_mint),
                   AVG(EXTRACT(EPOCH FROM (observed_at-prev_at)))
                       FILTER (WHERE prev_at IS NOT NULL),
                   COUNT(*) FILTER (WHERE social_confirmed),
                   (SELECT wins FROM signals),
                   (SELECT closed - wins FROM signals),
                   (SELECT CASE WHEN closed=0 THEN NULL ELSE wins::numeric/closed END FROM signals)
               FROM buys""",
            (wallet_address, wallet_address),
        )
        row = cursor.fetchone()
        observed, distinct_tokens, avg_interval, social, wins, losses, win_rate = row
        wins = int(wins or 0)
        losses = int(losses or 0)
        success = wins
        total = wins + losses
        reputation = Decimal(str(win_rate)) if win_rate is not None else Decimal("0")

        cursor.execute(
            """SELECT COUNT(*) FROM funding_ledger fl
               JOIN tracked_wallets tw ON tw.id=fl.destination_wallet_id
               WHERE tw.wallet_address=%s AND fl.source_wallet_id IS NOT NULL""",
            (wallet_address,),
        )
        shared = int(cursor.fetchone()[0])

        cursor.execute(
            """INSERT INTO wallet_features
               (wallet_address, observed_buy_count, distinct_token_count,
                avg_inter_buy_seconds, shared_funder_count,
                social_confirmation_count, successful_signal_count,
                failed_signal_count, win_rate, reputation_score, updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
               ON CONFLICT (wallet_address) DO UPDATE SET
                 observed_buy_count=EXCLUDED.observed_buy_count,
                 distinct_token_count=EXCLUDED.distinct_token_count,
                 avg_inter_buy_seconds=EXCLUDED.avg_inter_buy_seconds,
                 shared_funder_count=EXCLUDED.shared_funder_count,
                 social_confirmation_count=EXCLUDED.social_confirmation_count,
                 successful_signal_count=EXCLUDED.successful_signal_count,
                 failed_signal_count=EXCLUDED.failed_signal_count,
                 win_rate=EXCLUDED.win_rate,
                 reputation_score=EXCLUDED.reputation_score,
                 updated_at=NOW()""",
            (
                wallet_address, int(observed or 0), int(distinct_tokens or 0),
                avg_interval, shared, int(social or 0), success, losses,
                win_rate, reputation,
            ),
        )
        conn.commit()

    return WalletFeatures(
        wallet_address, int(observed or 0), int(distinct_tokens or 0),
        Decimal(str(avg_interval)) if avg_interval is not None else None,
        shared, int(row[3] or 0), success, losses,
        Decimal(str(win_rate)) if win_rate is not None else None, reputation,
    )
