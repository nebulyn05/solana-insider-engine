from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from app.intelligence.clustering import (
    ClusterSignal,
    find_spatiotemporal_cluster,
)


def test_cluster_requires_distinct_warm_wallets() -> None:
    anchor = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        (1, "warm-a", "mint", anchor, Decimal("2"), "sig-a"),
        (2, "warm-b", "mint", anchor, Decimal("4"), "sig-b"),
        (3, "warm-c", "mint", anchor, Decimal("6"), "sig-c"),
    ]
    with patch("app.intelligence.clustering.get_connection") as connection:
        cursor = connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = rows
        signal = find_spatiotemporal_cluster("mint", anchor, 3, 30)

    assert signal is not None
    assert signal.event_count == 3
    assert signal.warm_wallets == ("warm-a", "warm-b", "warm-c")
    assert signal.representative_price == Decimal("4")


def test_cluster_does_not_trigger_below_threshold() -> None:
    anchor = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with patch("app.intelligence.clustering.get_connection") as connection:
        cursor = connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            (1, "warm-a", "mint", anchor, Decimal("2"), "sig-a"),
            (2, "warm-b", "mint", anchor, Decimal("4"), "sig-b"),
        ]
        assert find_spatiotemporal_cluster("mint", anchor, 3, 30) is None
