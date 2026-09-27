from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class MonteCarloSummary:
    runs: int
    mean_pnl_sol: Decimal
    median_pnl_sol: Decimal
    p05_pnl_sol: Decimal
    p95_pnl_sol: Decimal
    probability_of_loss: Decimal
    max_drawdown_p95_sol: Decimal


def run_monte_carlo(
    trade_returns: list[Decimal],
    runs: int = 10000,
    seed: int = 7,
) -> MonteCarloSummary:
    if not trade_returns:
        raise ValueError("trade_returns cannot be empty")
    if runs < 1:
        raise ValueError("runs must be positive")
    rng = random.Random(seed)
    results: list[Decimal] = []
    drawdowns: list[Decimal] = []

    for _ in range(runs):
        sample = [rng.choice(trade_returns) for _ in trade_returns]
        equity = Decimal("0")
        peak = Decimal("0")
        max_dd = Decimal("0")
        for value in sample:
            equity += value
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)
        results.append(equity)
        drawdowns.append(max_dd)

    results.sort()
    drawdowns.sort()

    def pct(values: list[Decimal], p: Decimal) -> Decimal:
        idx = int((len(values) - 1) * p)
        return values[idx]

    mean = sum(results, Decimal("0")) / Decimal(len(results))
    probability_loss = Decimal(sum(v < 0 for v in results)) / Decimal(len(results))
    return MonteCarloSummary(
        runs=runs,
        mean_pnl_sol=mean,
        median_pnl_sol=pct(results, Decimal("0.50")),
        p05_pnl_sol=pct(results, Decimal("0.05")),
        p95_pnl_sol=pct(results, Decimal("0.95")),
        probability_of_loss=probability_loss,
        max_drawdown_p95_sol=pct(drawdowns, Decimal("0.95")),
    )
