from decimal import Decimal
from unittest.mock import patch

from app.intelligence.ancestry.engine import (
    _find_source_from_balances,
    trace_ancestry,
)


def test_find_source_from_balances_identifies_largest_funder() -> None:
    transaction = {
        "transaction": {
            "message": {
                "accountKeys": [
                    {"pubkey": "destination"},
                    {"pubkey": "source-a"},
                    {"pubkey": "source-b"},
                ]
            }
        },
        "meta": {
            "preBalances": [100, 2_000, 3_000],
            "postBalances": [1_100, 1_900, 3_000],
        },
    }

    result = _find_source_from_balances(transaction, "destination")

    assert result == ("source-a", Decimal("0.000001"))


def test_trace_stops_when_flagged_root_is_found() -> None:
    signatures = [{"signature": "sig-a", "slot": 100, "err": None}]
    transaction = {
        "transaction": {
            "message": {
                "accountKeys": [
                    {"pubkey": "wallet"},
                    {"pubkey": "flagged"},
                ]
            }
        },
        "meta": {
            "preBalances": [0, 5_000],
            "postBalances": [5_000, 0],
        },
    }

    def fake_rpc(method: str, params: list[object]) -> object:
        if method == "getSignaturesForAddress":
            return signatures
        if method == "getTransaction":
            return transaction
        raise AssertionError(method)

    with patch(
        "app.intelligence.ancestry.engine._rpc",
        side_effect=fake_rpc,
    ), patch(
        "app.intelligence.ancestry.engine._classify_root",
        side_effect=lambda wallet: type(
            "Classification",
            (),
            {
                "wallet": wallet,
                "flagged": wallet == "flagged",
                "reason": "cex" if wallet == "flagged" else None,
                "label": "configured-cex" if wallet == "flagged" else None,
            },
        )():
    ):
        result = trace_ancestry("wallet")

    assert result.root_wallet == "flagged"
    assert result.root_classification.flagged is True
    assert len(result.edges) == 1
