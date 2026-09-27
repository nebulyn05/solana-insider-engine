from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable

from websockets.asyncio.server import ServerConnection, serve

from app.social.models import SocialPost
from app.social.repository import persist_post

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SocialSubscription:
    source_type: str
    source_key: str

    def matches(self, source_type: str, source_key: str) -> bool:
        return self.source_type == source_type and self.source_key == source_key


class SocialWebSocketIngestor:
    def __init__(
        self,
        subscriptions: list[SocialSubscription],
        on_post: Callable[[SocialPost], Awaitable[None]] | None = None,
    ) -> None:
        if not subscriptions:
            raise ValueError("at least one social subscription is required")
        self._subscriptions = tuple(subscriptions)
        self._on_post = on_post

    async def handler(self, websocket: ServerConnection) -> None:
        async for message in websocket:
            try:
                payload = json.loads(message)
                post = self._parse(payload)
                if not self._is_allowed(post):
                    await websocket.send(
                        json.dumps({"ok": False, "error": "source_not_subscribed"})
                    )
                    continue

                inserted = persist_post(post)
                if self._on_post is not None:
                    await self._on_post(post)

                await websocket.send(
                    json.dumps(
                        {
                            "ok": True,
                            "inserted": inserted,
                            "external_id": post.external_id,
                        }
                    )
                )
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                await websocket.send(json.dumps({"ok": False, "error": str(exc)}))

    def _is_allowed(self, post: SocialPost) -> bool:
        return any(
            subscription.matches(post.source_type, post.source_key)
            for subscription in self._subscriptions
        )

    @staticmethod
    def _parse(payload: dict[str, Any]) -> SocialPost:
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
        published_at = datetime.fromisoformat(
            str(payload["published_at"]).replace("Z", "+00:00")
        )
        post = SocialPost(
            source_type=str(payload["source_type"]),
            source_key=str(payload["source_key"]),
            external_id=str(payload["external_id"]),
            text_content=str(payload["text_content"]),
            published_at=published_at,
            author_key=(
                str(payload["author_key"])
                if payload.get("author_key") is not None
                else None
            ),
            raw_payload=payload.get("raw_payload") or {},
        )
        post.validate()
        return post


async def run_social_websocket(
    host: str,
    port: int,
    subscriptions: list[SocialSubscription],
) -> None:
    ingestor = SocialWebSocketIngestor(subscriptions)
    async with serve(ingestor.handler, host, port):
        logger.info(
            "social websocket listening on ws://%s:%s for %d subscriptions",
            host,
            port,
            len(subscriptions),
        )
        await asyncio.Future()
