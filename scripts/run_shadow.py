import argparse
from decimal import Decimal

from app.intelligence.shadow import LocalShadowSimulator, ShadowTokenModel


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local paper-only shadow simulator.")
    parser.add_argument("token_mint")
    parser.add_argument("buy_price", type=Decimal)
    parser.add_argument("notional_sol", type=Decimal)
    parser.add_argument("--liquidity-sol", type=Decimal, default=Decimal("100"))
    parser.add_argument("--buy-fee-bps", type=Decimal, default=Decimal("0"))
    parser.add_argument("--sell-fee-bps", type=Decimal, default=Decimal("0"))
    parser.add_argument("--sell-disabled", action="store_true")
    parser.add_argument("--max-sell-fraction", type=Decimal, default=Decimal("1"))
    args = parser.parse_args()

    result = LocalShadowSimulator().run(
        ShadowTokenModel(
            token_mint=args.token_mint,
            buy_price=args.buy_price,
            liquidity_sol=args.liquidity_sol,
            buy_fee_bps=args.buy_fee_bps,
            sell_fee_bps=args.sell_fee_bps,
            sell_enabled=not args.sell_disabled,
            max_sell_fraction=args.max_sell_fraction,
        ),
        args.notional_sol,
    )

    print(
        f"sellable={result.sellable} "
        f"pnl_sol={result.round_trip_pnl_sol} "
        f"return_bps={result.round_trip_return_bps} "
        f"reason={result.rejection_reason or 'none'}"
    )
    return 0 if result.sellable else 1


if __name__ == "__main__":
    raise SystemExit(main())
