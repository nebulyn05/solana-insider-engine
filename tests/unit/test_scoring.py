from decimal import Decimal

from app.intelligence.scoring import score_signal


def test_signal_score_is_bounded_and_weighted() -> None:
    result = score_signal(
        "s1",
        "mint",
        {
            "funding_lineage": Decimal("1"),
            "warm_cluster": Decimal("1"),
        },
        persist=False,
    )
    assert result.score == Decimal("45")
    assert result.components["funding_lineage"] == Decimal("25")
    assert result.components["warm_cluster"] == Decimal("20")
