from __future__ import annotations

import argparse
from decimal import Decimal

from app.replay.monte_carlo import run_monte_carlo


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Monte Carlo on a supplied return series.")
    parser.add_argument("returns", nargs="+", help="Per-trade P&L values in SOL.")
    parser.add_argument("--runs", type=int, default=10000)
    args = parser.parse_args()
    summary = run_monte_carlo([Decimal(v) for v in args.returns], runs=args.runs)
    print(summary)


if __name__ == "__main__":
    main()
