from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Iterable


@dataclass(frozen=True)
class StrategyResult:
    name: str
    trades: int
    pnl_sol: Decimal
    win_rate: Decimal | None


def compare_trade_returns(
    strategies: dict[str, Iterable[Decimal]],
) -> tuple[StrategyResult, ...]:
    results = []
    for name, values in strategies.items():
        returns = list(values)
        wins = sum(v > 0 for v in returns)
        results.append(
            StrategyResult(
                name=name,
                trades=len(returns),
                pnl_sol=sum(returns, Decimal("0")),
                win_rate=(Decimal(wins) / Decimal(len(returns))) if returns else None,
            )
        )
    return tuple(results)


def paired_delta(
    baseline: Iterable[Decimal],
    candidate: Iterable[Decimal],
) -> Decimal:
    base = list(baseline)
    test = list(candidate)
    if len(base) != len(test):
        raise ValueError("strategies must contain the same number of observations")
    return sum(test, Decimal("0")) - sum(base, Decimal("0"))
