from __future__ import annotations

import asyncio
import json
from datetime import timezone

from app.social.models import SocialPost
from app.social.solana_mints import extract_solana_mints
from app.social.websocket import SocialSubscription, SocialWebSocketIngestor


def test_extract_solana_mints_deduplicates_and_ignores_invalid_chars() -> None:
    mint = "So11111111111111111111111111111111111111112"
    text = f"buy {mint} then {mint}"
    assert extract_solana_mints(text) == [mint]


def test_subscription_matches_exact_source() -> None:
    subscription = SocialSubscription("x", "developer_one")
    assert subscription.matches("x", "developer_one")
    assert not subscription.matches("x", "developer_two")
    assert not subscription.matches("telegram", "developer_one")


def test_websocket_payload_is_parsed() -> None:
    ingestor = SocialWebSocketIngestor([SocialSubscription("telegram", "-100123")])
    payload = {
        "source_type": "telegram",
        "source_key": "-100123",
        "external_id": "42",
        "author_key": "caller",
        "published_at": "2026-09-27T10:00:00Z",
        "text_content": "mint",
        "raw_payload": {"chat_id": -100123},
    }
    post = ingestor._parse(payload)
    assert isinstance(post, SocialPost)
    assert post.published_at.tzinfo == timezone.utc
    assert post.external_id == "42"


def test_websocket_handler_rejects_unsubscribed_source(monkeypatch) -> None:
    ingestor = SocialWebSocketIngestor([SocialSubscription("x", "dev")])

    class FakeSocket:
        def __init__(self) -> None:
            self.sent: list[str] = []
            self.messages = [
                json.dumps(
                    {
                        "source_type": "telegram",
                        "source_key": "group",
                        "external_id": "1",
                        "published_at": "2026-09-27T10:00:00Z",
                        "text_content": "mint",
                    }
                )
            ]

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.messages:
                raise StopAsyncIteration
            return self.messages.pop(0)

        async def send(self, message: str) -> None:
            self.sent.append(message)

    socket = FakeSocket()

    async def run() -> None:
        await ingestor.handler(socket)  # type: ignore[arg-type]

    asyncio.run(run())
    response = json.loads(socket.sent[0])
    assert response == {"ok": False, "error": "source_not_subscribed"}
