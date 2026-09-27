from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.database.connection import get_connection


MIN_DELAY = timedelta(minutes=1)
MAX_DELAY = timedelta(minutes=10)


@dataclass(frozen=True)
class SocialConfirmation:
    buy_event_id: int
    wallet_address: str
    token_mint: str
    social_post_id: int
    source_type: str
    source_key: str
    published_at: datetime
    delay: timedelta


class SocialCoOccurrenceFilter:
    """Upgrades indexed-wallet buy events when designated social sources confirm them."""

    def __init__(
        self,
        min_delay: timedelta = MIN_DELAY,
        max_delay: timedelta = MAX_DELAY,
    ) -> None:
        if min_delay < timedelta(0):
            raise ValueError("min_delay must be non-negative")
        if max_delay < min_delay:
            raise ValueError("max_delay must be >= min_delay")
        self.min_delay = min_delay
        self.max_delay = max_delay

    def evaluate_buy_event(self, buy_event_id: int) -> SocialConfirmation | None:
        if buy_event_id <= 0:
            raise ValueError("buy_event_id must be positive")

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        t.id,
                        t.wallet_address,
                        t.token_mint,
                        t.observed_at,
                        t.social_confirmed,
                        sp.id,
                        ss.source_type,
                        ss.source_key,
                        sp.published_at
                    FROM token_buy_events t
                    JOIN tracked_wallets tw
                      ON tw.wallet_address = t.wallet_address
                     AND tw.is_tracked = TRUE
                    JOIN social_posts sp
                      ON t.token_mint = ANY(sp.token_mints)
                     AND sp.published_at >= t.observed_at + %s
                     AND sp.published_at <= t.observed_at + %s
                    JOIN social_sources ss
                      ON ss.id = sp.source_id
                     AND ss.enabled = TRUE
                    WHERE t.id = %s
                    ORDER BY sp.published_at ASC, sp.id ASC
                    LIMIT 1
                    """,
                    (
                        self.min_delay,
                        self.max_delay,
                        buy_event_id,
                    ),
                )
                row = cursor.fetchone()
                if row is None:
                    return None

                (
                    event_id,
                    wallet_address,
                    token_mint,
                    observed_at,
                    already_confirmed,
                    social_post_id,
                    source_type,
                    source_key,
                    published_at,
                ) = row

                if not already_confirmed:
                    cursor.execute(
                        """
                        UPDATE token_buy_events
                        SET confidence_level = 'SOCIAL_CONFIRMED',
                            social_confirmed = TRUE,
                            social_confirmed_at = %s,
                            social_post_id = %s
                        WHERE id = %s
                          AND social_confirmed = FALSE
                        """,
                        (published_at, social_post_id, event_id),
                    )

                return SocialConfirmation(
                    buy_event_id=int(event_id),
                    wallet_address=wallet_address,
                    token_mint=token_mint,
                    social_post_id=int(social_post_id),
                    source_type=source_type,
                    source_key=source_key,
                    published_at=published_at,
                    delay=published_at - observed_at,
                )

    def evaluate_pending(self, limit: int = 100) -> list[SocialConfirmation]:
        if limit <= 0:
            raise ValueError("limit must be positive")

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT t.id
                    FROM token_buy_events t
                    JOIN tracked_wallets tw
                      ON tw.wallet_address = t.wallet_address
                     AND tw.is_tracked = TRUE
                    WHERE t.social_confirmed = FALSE
                    ORDER BY t.observed_at ASC, t.id ASC
                    LIMIT %s
                    """,
                    (limit,),
                )
                ids = [int(row[0]) for row in cursor.fetchall()]

        confirmations: list[SocialConfirmation] = []
        for event_id in ids:
            match = self.evaluate_buy_event(event_id)
            if match is not None:
                confirmations.append(match)
        return confirmations
