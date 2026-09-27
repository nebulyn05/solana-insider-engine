from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.database.connection import get_connection
from app.events.bus import EngineEvent
from app.execution.slippage import ExecutionConditions, estimate_buy_price
from app.intelligence.scoring import score_signal
from app.intelligence.sliding_clustering import find_best_sliding_window_cluster
from app.simulation.position_manager import manage_open_positions

DEFAULT_NOTIONAL_SOL = Decimal("1")
DEFAULT_SIGNAL_THRESHOLD = Decimal("30")


def _decimal_env(name: str, default: Decimal) -> Decimal:
    value = os.getenv(name)
    return default if value is None else Decimal(value)


def _cluster_features(token_mint: str, wallets: tuple[str, ...], window_start: datetime, window_end: datetime) -> dict[str, Decimal]:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """SELECT COALESCE(AVG(wf.reputation_score),0),
                      COUNT(*) FILTER (WHERE e.social_confirmed)
               FROM token_buy_events e
               LEFT JOIN wallet_features wf ON wf.wallet_address=e.wallet_address
               WHERE e.token_mint=%s
                 AND e.observed_at BETWEEN %s AND %s
                 AND e.wallet_address = ANY(%s)""",
            (token_mint, window_start, window_end, list(wallets)),
        )
        reputation, social = cursor.fetchone()

    span = max(0.001, (window_end - window_start).total_seconds())
    return {
        "warm_cluster": min(Decimal("1"), Decimal(len(wallets)) / Decimal("5")),
        "social_confirmation": Decimal("1") if int(social or 0) > 0 else Decimal("0"),
        "timing_compression": max(Decimal("0"), Decimal("1") - Decimal(str(span / 30.0))),
        "funding_lineage": Decimal("0"),
        "shared_first_funder": Decimal("0"),
        "deployer_relation": Decimal("0"),
        "wallet_reputation": Decimal(str(reputation or 0)),
    }


def _insert_paper_entry(
    signal_id: str,
    token_mint: str,
    wallet_address: str,
    requested_price: Decimal,
    detected_at: datetime,
    score: Decimal,
    metadata: dict[str, Any],
) -> bool:
    notional = _decimal_env("PAPER_NOTIONAL_SOL", DEFAULT_NOTIONAL_SOL)
    liquidity = _decimal_env("PAPER_LIQUIDITY_SOL", Decimal("100"))
    volatility = _decimal_env("PAPER_VOLATILITY_BPS", Decimal("100"))
    latency = _decimal_env("PAPER_NETWORK_DELAY_MS", Decimal("100"))

    estimate = estimate_buy_price(
        requested_price,
        ExecutionConditions(
            liquidity_sol=liquidity,
            notional_sol=notional,
            volatility_bps=volatility,
            network_delay_ms=latency,
        ),
    )
    quantity = notional / estimate.execution_price

    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """INSERT INTO token_metadata(mint_address,network)
               VALUES(%s,'mainnet-beta')
               ON CONFLICT(mint_address) DO NOTHING""",
            (token_mint,),
        )
        cursor.execute(
            """SELECT id FROM tracked_wallets
               WHERE wallet_address=%s AND network='mainnet-beta'
               LIMIT 1""",
            (wallet_address,),
        )
        wallet_row = cursor.fetchone()
        wallet_id = wallet_row[0] if wallet_row else None

        cursor.execute(
            """INSERT INTO simulated_trades
               (trade_id,wallet_id,token_mint,side,status,quantity,
                requested_price,executed_price,requested_notional,
                executed_notional,slippage_bps,slippage_amount,
                signal_id,signal_created_at,detected_at,
                entry_latency_ms,decision_latency_ms,execution_latency_ms,
                total_latency_ms,metadata)
               VALUES(gen_random_uuid(),%s,%s,'BUY','OPEN',%s,%s,%s,%s,%s,
                      %s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
               ON CONFLICT(signal_id) DO NOTHING
               RETURNING trade_id""",
            (
                wallet_id, token_mint, quantity, requested_price,
                estimate.execution_price, notional,
                notional, estimate.total_bps,
                estimate.execution_price - requested_price,
                signal_id, detected_at, detected_at,
                Decimal("0"), Decimal("0"), latency,
                latency, json.dumps({
                    **metadata,
                    "detector": "live_mainnet_pipeline",
                    "execution": "paper",
                    "network": "mainnet-beta",
                    "signal_score": str(score),
                    "slippage": {
                        "total_bps": str(estimate.total_bps),
                        "liquidity_impact_bps": str(estimate.liquidity_impact_bps),
                        "volatility_bps": str(estimate.volatility_bps),
                        "latency_bps": str(estimate.latency_bps),
                    },
                }),
            ),
        )
        row = cursor.fetchone()
        if row is None:
            conn.rollback()
            return False

        cursor.execute(
            """INSERT INTO execution_events(signal_id,trade_id,event_type,event_at,metadata)
               VALUES(%s,%s,'ENTRY',%s,%s::jsonb)""",
            (
                signal_id, str(row[0]), detected_at,
                json.dumps({"score": str(score), "paper": True}),
            ),
        )
        conn.commit()
        return True


class LivePaperPipeline:
    """Durable application boundary between live observations and paper execution."""

    def __init__(self) -> None:
        self.threshold = _decimal_env("SIGNAL_THRESHOLD", DEFAULT_SIGNAL_THRESHOLD)

    async def handle(self, event: EngineEvent) -> None:
        if event.event_type != "BUY_OBSERVED":
            return

        payload = event.payload
        token_mint = str(payload["token_mint"])
        observed_at = event.utc_time
        cluster = find_best_sliding_window_cluster(
            token_mint,
            observed_at - timedelta(seconds=30),
            observed_at,
            min_warm_wallets=int(os.getenv("MIN_WARM_WALLETS", "3")),
            window_seconds=int(os.getenv("CLUSTER_WINDOW_SECONDS", "30")),
        )
        if cluster is None:
            return

        features = _cluster_features(
            token_mint, cluster.warm_wallets,
            cluster.window_start, cluster.window_end,
        )
        score = score_signal(
            signal_id=f"cluster:{token_mint}:{cluster.window_start.isoformat()}:{cluster.window_end.isoformat()}",
            token_mint=token_mint,
            features=features,
            persist=True,
        )
        if score.score < self.threshold:
            return

        _insert_paper_entry(
            score.signal_id,
            token_mint,
            cluster.warm_wallets[0],
            cluster.representative_price,
            observed_at,
            score.score,
            {
                "wallets": list(cluster.warm_wallets),
                "event_count": cluster.event_count,
                "confidence": payload.get("confidence"),
                "dex_name": payload.get("dex_name"),
                "transaction_signature": payload.get("signature"),
            },
        )

    async def monitor_positions(self) -> int:
        return manage_open_positions()
