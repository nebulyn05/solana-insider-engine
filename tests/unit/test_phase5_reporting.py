from datetime import datetime, timezone
from decimal import Decimal

from app.reporting.phase5 import (
    PHASE5_DETECTOR,
    TradeDiagnostic,
    calculate_metrics,
)


def trade(
    status: str,
    pnl: str | None,
    notional: str = "1",
    slippage_bps: str = "400",
    metadata: dict | None = None,
) -> TradeDiagnostic:
    return TradeDiagnostic(
        status=status,
        realized_pnl=None if pnl is None else Decimal(pnl),
        requested_notional=Decimal(notional),
        slippage_bps=Decimal(slippage_bps),
        metadata=metadata or {},
    )


def test_calculates_core_performance_metrics() -> None:
    metrics = calculate_metrics(
        [
            trade("CLOSED", "0.25", metadata={"outcome": "WIN"}),
            trade("CLOSED", "-0.10", metadata={"outcome": "LOSS"}),
            trade("OPEN", None),
        ],
        generated_at=datetime(2026, 9, 27, tzinfo=timezone.utc),
    )

    assert metrics.detector == PHASE5_DETECTOR
    assert metrics.total_entries == 3
    assert metrics.closed_entries == 2
    assert metrics.open_entries == 1
    assert metrics.net_paper_pnl_sol == Decimal("0.15")
    assert metrics.win_count == 1
    assert metrics.loss_count == 1
    assert metrics.win_rate == Decimal("0.5")
    assert metrics.false_positive_data_complete is True
    assert metrics.false_positive_bot_ratio == Decimal("0")
    assert metrics.average_slippage_bps == Decimal("400")
    assert metrics.slip_degradation_factor == Decimal("1.04")


def test_false_positive_ratio_requires_explicit_outcomes() -> None:
    metrics = calculate_metrics(
        [
            trade("CLOSED", "0.20", metadata={"outcome": "WIN"}),
            trade("CLOSED", "-0.05"),
        ]
    )

    assert metrics.false_positive_data_complete is False
    assert metrics.false_positive_count == 0
    assert metrics.false_positive_bot_ratio is None


def test_false_positive_metadata_is_counted() -> None:
    metrics = calculate_metrics(
        [
            trade("CLOSED", "-0.20", metadata={"outcome": "FALSE_POSITIVE"}),
            trade("CLOSED", "0.10", metadata={"outcome": "WIN"}),
            trade("CANCELLED", None, metadata={"outcome": "FALSE_POSITIVE"}),
        ]
    )

    assert metrics.false_positive_data_complete is True
    assert metrics.false_positive_count == 1
    assert metrics.false_positive_bot_ratio == Decimal("0.5")
    assert metrics.cancelled_entries == 1


def test_empty_dataset_returns_neutral_diagnostics() -> None:
    metrics = calculate_metrics([])

    assert metrics.total_entries == 0
    assert metrics.closed_entries == 0
    assert metrics.net_paper_pnl_sol == Decimal("0")
    assert metrics.win_rate is None
    assert metrics.false_positive_bot_ratio is None
    assert metrics.average_slippage_bps is None
    assert metrics.slip_degradation_factor is None
