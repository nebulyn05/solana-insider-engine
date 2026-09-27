from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class SocialSource:
    source_type: str
    source_key: str
    display_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.source_type not in {"x", "telegram"}:
            raise ValueError("source_type must be 'x' or 'telegram'")
        if not self.source_key:
            raise ValueError("source_key is required")


@dataclass(frozen=True)
class SocialPost:
    source_type: str
    source_key: str
    external_id: str
    text_content: str
    published_at: datetime
    author_key: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.source_type not in {"x", "telegram"}:
            raise ValueError("source_type must be 'x' or 'telegram'")
        if not self.source_key:
            raise ValueError("source_key is required")
        if not self.external_id:
            raise ValueError("external_id is required")
        if not self.text_content:
            raise ValueError("text_content is required")
        if self.published_at.tzinfo is None:
            raise ValueError("published_at must be timezone-aware")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
