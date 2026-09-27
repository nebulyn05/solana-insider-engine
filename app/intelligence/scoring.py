from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json

from app.database.connection import get_connection


@dataclass(frozen=True)
class SignalScore:
    signal_id: str
    token_mint: str
    score: Decimal
    components: dict[str, Decimal]


DEFAULT_WEIGHTS = {
    "funding_lineage": Decimal("25"),
    "shared_first_funder": Decimal("20"),
    "warm_cluster": Decimal("20"),
    "social_confirmation": Decimal("10"),
    "deployer_relation": Decimal("15"),
    "timing_compression": Decimal("10"),
}


def _clamp(value: Decimal) -> Decimal:
    return max(Decimal("0"), min(Decimal("1"), value))


def score_signal(
    signal_id: str,
    token_mint: str,
    features: dict[str, Decimal],
    weights: dict[str, Decimal] | None = None,
    persist: bool = True,
) -> SignalScore:
    if not signal_id or not token_mint:
        raise ValueError("signal_id and token_mint are required")
    active = weights or DEFAULT_WEIGHTS
    components = {
        key: active[key] * _clamp(Decimal(str(features.get(key, Decimal("0")))))
        for key in active
    }
    total = min(Decimal("100"), sum(components.values(), Decimal("0")))
    result = SignalScore(signal_id, token_mint, total, components)

    if persist:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """INSERT INTO signal_scores (signal_id, token_mint, score, components)
                   VALUES (%s, %s, %s, %s::jsonb)
                   ON CONFLICT (signal_id) DO UPDATE
                   SET score=EXCLUDED.score, components=EXCLUDED.components""",
                (
                    signal_id, token_mint, total,
                    json.dumps({k: str(v) for k, v in components.items()}),
                ),
            )
            conn.commit()
    return result
