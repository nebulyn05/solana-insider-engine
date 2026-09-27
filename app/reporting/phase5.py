from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from app.database.connection import get_connection

LOGGER = logging.getLogger("phase5.reporting")

PHASE5_DETECTOR = "phase5_48h_simulation"
VALID_OUTCOMES = {"WIN", "LOSS", "FALSE_POSITIVE"}


@dataclass(frozen=True)
class TradeDiagnostic:
    status: str
    realized_pnl: Decimal | None
    requested_notional: Decimal | None
    slippage_bps: Decimal
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class PerformanceMetrics:
    detector: str
    generated_at: datetime
    total_entries: int
    closed_entries: int
    open_entries: int
    cancelled_entries: int
    net_paper_pnl_sol: Decimal
    win_count: int
    loss_count: int
    win_rate: Decimal | None
    false_positive_count: int
    false_positive_bot_ratio: Decimal | None
    false_positive_data_complete: bool
    total_requested_notional_sol: Decimal
    average_slippage_bps: Decimal | None
    slip_degradation_factor: Decimal | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "detector": self.detector,
            "generated_at": self.generated_at.isoformat(),
            "total_entries": self.total_entries,
            "closed_entries": self.closed_entries,
            "open_entries": self.open_entries,
            "cancelled_entries": self.cancelled_entries,
            "net_paper_pnl_sol": str(self.net_paper_pnl_sol),
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "win_rate": _decimal_or_none(self.win_rate),
            "false_positive_count": self.false_positive_count,
            "false_positive_bot_ratio": _decimal_or_none(self.false_positive_bot_ratio),
            "false_positive_data_complete": self.false_positive_data_complete,
            "total_requested_notional_sol": str(self.total_requested_notional_sol),
            "average_slippage_bps": _decimal_or_none(self.average_slippage_bps),
            "slip_degradation_factor": _decimal_or_none(self.slip_degradation_factor),
        }


def _decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid decimal value: {value!r}") from exc


def _decimal_or_none(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _normalise_metadata(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, Mapping):
            return parsed
    raise ValueError("trade metadata must be a JSON object")


def _explicit_outcome(trade: TradeDiagnostic) -> str | None:
    outcome = str(trade.metadata.get("outcome", "")).strip().upper()
    if outcome in VALID_OUTCOMES:
        return outcome
    if trade.metadata.get("false_positive") is True:
        return "FALSE_POSITIVE"
    return None


def calculate_metrics(
    trades: Iterable[TradeDiagnostic],
    detector: str = PHASE5_DETECTOR,
    generated_at: datetime | None = None,
) -> PerformanceMetrics:
    entries = list(trades)
    closed = [trade for trade in entries if trade.status == "CLOSED"]
    open_entries = sum(trade.status == "OPEN" for trade in entries)
    cancelled = sum(trade.status == "CANCELLED" for trade in entries)

    net_pnl = sum(
        (_decimal(trade.realized_pnl) for trade in closed if trade.realized_pnl is not None),
        Decimal("0"),
    )
    wins = sum(
        trade.realized_pnl is not None and _decimal(trade.realized_pnl) > 0
        for trade in closed
    )
    losses = sum(
        trade.realized_pnl is not None and _decimal(trade.realized_pnl) <= 0
        for trade in closed
    )

    win_rate = (
        Decimal(wins) / Decimal(len(closed))
        if closed
        else None
    )

    explicit_outcomes = [_explicit_outcome(trade) for trade in closed]
    outcome_complete = bool(closed) and all(outcome is not None for outcome in explicit_outcomes)
    false_positive_count = sum(outcome == "FALSE_POSITIVE" for outcome in explicit_outcomes)
    false_positive_ratio = (
        Decimal(false_positive_count) / Decimal(len(closed))
        if outcome_complete
        else None
    )

    requested_notional = sum(
        (_decimal(trade.requested_notional) for trade in entries),
        Decimal("0"),
    )
    total_slippage_bps = sum(
        (_decimal(trade.slippage_bps) for trade in entries),
        Decimal("0"),
    )
    average_slippage_bps = (
        total_slippage_bps / Decimal(len(entries))
        if entries
        else None
    )

    # A factor of 1.04 means the simulated entry price was 4% worse than
    # the requested price. This is the price-degradation metric, independent
    # of notional sizing and therefore suitable for the fixed Phase 5 penalty.
    slip_degradation_factor = (
        Decimal("1") + (average_slippage_bps / Decimal("10000"))
        if average_slippage_bps is not None
        else None
    )

    timestamp = generated_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")

    return PerformanceMetrics(
        detector=detector,
        generated_at=timestamp.astimezone(timezone.utc),
        total_entries=len(entries),
        closed_entries=len(closed),
        open_entries=open_entries,
        cancelled_entries=cancelled,
        net_paper_pnl_sol=net_pnl,
        win_count=wins,
        loss_count=losses,
        win_rate=win_rate,
        false_positive_count=false_positive_count,
        false_positive_bot_ratio=false_positive_ratio,
        false_positive_data_complete=outcome_complete,
        total_requested_notional_sol=requested_notional,
        average_slippage_bps=average_slippage_bps,
        slip_degradation_factor=slip_degradation_factor,
    )


def load_phase5_trades(
    detector: str = PHASE5_DETECTOR,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[TradeDiagnostic]:
    clauses = [
        "side = 'BUY'",
        "metadata->>'detector' = %s",
    ]
    params: list[Any] = [detector]

    if since is not None:
        clauses.append("entry_at >= %s")
        params.append(since.astimezone(timezone.utc))

    if until is not None:
        clauses.append("entry_at < %s")
        params.append(until.astimezone(timezone.utc))

    query = f"""
        SELECT status, realized_pnl, requested_notional, slippage_bps, metadata
        FROM simulated_trades
        WHERE {' AND '.join(clauses)}
        ORDER BY entry_at ASC, id ASC
    """

    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(query, params)
        return [
            TradeDiagnostic(
                status=row[0],
                realized_pnl=row[1],
                requested_notional=row[2],
                slippage_bps=row[3],
                metadata=_normalise_metadata(row[4]),
            )
            for row in cursor.fetchall()
        ]


def build_report(
    detector: str = PHASE5_DETECTOR,
    since: datetime | None = None,
    until: datetime | None = None,
) -> PerformanceMetrics:
    return calculate_metrics(
        load_phase5_trades(detector=detector, since=since, until=until),
        detector=detector,
    )


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("datetime must include a timezone")
    return parsed.astimezone(timezone.utc)


def _format_ratio(value: Decimal | None) -> str:
    return "N/A" if value is None else f"{value * Decimal('100'):.2f}%"


def print_report(metrics: PerformanceMetrics) -> None:
    print("Phase 5 Simulation Performance")
    print("=" * 34)
    print(f"Detector:                 {metrics.detector}")
    print(f"Generated:                {metrics.generated_at.isoformat()}")
    print(f"Total entries:            {metrics.total_entries}")
    print(f"Closed entries:           {metrics.closed_entries}")
    print(f"Open entries:             {metrics.open_entries}")
    print(f"Cancelled entries:        {metrics.cancelled_entries}")
    print(f"Net Paper P&L (SOL):      {metrics.net_paper_pnl_sol}")
    print(f"Win Rate:                 {_format_ratio(metrics.win_rate)}")
    if metrics.false_positive_data_complete:
        print(f"False Positive Bot Ratio: {_format_ratio(metrics.false_positive_bot_ratio)}")
    else:
        print("False Positive Bot Ratio: N/A (explicit outcome labels incomplete)")
    print(f"Avg. Slippage (bps):      {metrics.average_slippage_bps if metrics.average_slippage_bps is not None else 'N/A'}")
    print(f"Slip Degradation Factor:  {metrics.slip_degradation_factor if metrics.slip_degradation_factor is not None else 'N/A'}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Report Phase 5 paper-trading performance diagnostics."
    )
    parser.add_argument("--detector", default=PHASE5_DETECTOR)
    parser.add_argument("--since", type=_parse_datetime)
    parser.add_argument("--until", type=_parse_datetime)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    metrics = build_report(
        detector=args.detector,
        since=args.since,
        until=args.until,
    )

    if args.as_json:
        print(json.dumps(metrics.as_dict(), indent=2))
    else:
        print_report(metrics)


if __name__ == "__main__":
    main()
