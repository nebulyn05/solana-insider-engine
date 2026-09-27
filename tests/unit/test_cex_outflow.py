from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from app.ingestion.normalizers.cex_outflow import CexOutflow, enrich_freshness


def test_enrich_freshness_keeps_only_chain_fresh_wallets() -> None:
    events = [
        CexOutflow("sig", 10, "source", "fresh", Decimal("1"), uuid4()),
        CexOutflow("sig2", 11, "source", "old", Decimal("2"), uuid4()),
    ]
    with patch(
        "app.ingestion.normalizers.cex_outflow._fresh_from_rpc",
        side_effect=[True, False],
    ):
        import asyncio
        result = asyncio.run(enrich_freshness(events))

    assert [event.destination_wallet for event in result] == ["fresh"]
    assert result[0].fresh_on_chain is True
