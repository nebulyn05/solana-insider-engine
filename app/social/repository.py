from __future__ import annotations

from datetime import datetime
from typing import Any

from app.database.connection import get_connection
from app.social.models import SocialPost, SocialSource
from app.social.solana_mints import extract_solana_mints


def upsert_source(source: SocialSource) -> int:
    source.validate()
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO social_sources (
                    source_type, source_key, display_name, metadata
                )
                VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (source_type, source_key)
                DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    metadata = EXCLUDED.metadata,
                    enabled = TRUE,
                    updated_at = NOW()
                RETURNING id
                """,
                (
                    source.source_type,
                    source.source_key,
                    source.display_name,
                    _json(source.metadata),
                ),
            )
            return int(cursor.fetchone()[0])


def persist_post(post: SocialPost) -> bool:
    post.validate()
    source_id = upsert_source(
        SocialSource(
            source_type=post.source_type,
            source_key=post.source_key,
        )
    )
    mints = extract_solana_mints(post.text_content)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO social_posts (
                    source_id, external_id, author_key, published_at,
                    text_content, token_mints, raw_payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (source_id, external_id) DO NOTHING
                RETURNING id
                """,
                (
                    source_id,
                    post.external_id,
                    post.author_key,
                    post.published_at,
                    post.text_content,
                    mints,
                    _json(post.raw_payload),
                ),
            )
            return cursor.fetchone() is not None


def _json(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, separators=(",", ":"), sort_keys=True)
