import argparse
import json

from app.intelligence.onchain_shadow import OnChainShadowSimulator


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Simulate supplied Solana instructions without broadcasting."
    )
    parser.add_argument("transaction_base64")
    parser.add_argument(
        "--account",
        action="append",
        default=[],
        help="Account address whose post-simulation state should be returned.",
    )
    parser.add_argument("--sell-transaction-base64")
    parser.add_argument(
        "--atomic-round-trip",
        action="store_true",
        help="Treat transaction_base64 as a single BUY-then-SELL transaction.",
    )
    args = parser.parse_args()

    simulator = OnChainShadowSimulator()
    accounts = tuple(args.account)

    if args.atomic_round_trip:
        verdict = simulator.simulate_atomic_round_trip(
            args.transaction_base64,
            accounts,
        )
    else:
        verdict = simulator.simulate_round_trip(
            args.transaction_base64,
            args.sell_transaction_base64,
            accounts,
        )

    output = {
        "sellable": verdict.sellable,
        "reason": verdict.reason,
        "buy": {
            "success": verdict.buy.success,
            "slot": verdict.buy.slot,
            "error": verdict.buy.error,
            "units_consumed": verdict.buy.units_consumed,
            "fee_lamports": verdict.buy.fee_lamports,
            "invoked_programs": verdict.buy.invoked_programs,
            "token_balance_deltas": [
                {
                    "account_index": item.account_index,
                    "mint": item.mint,
                    "owner": item.owner,
                    "before": str(item.before),
                    "after": str(item.after),
                    "delta": str(item.delta),
                }
                for item in verdict.buy.token_balance_deltas
            ],
        },
        "sell": (
            {
                "success": verdict.sell.success,
                "slot": verdict.sell.slot,
                "error": verdict.sell.error,
                "units_consumed": verdict.sell.units_consumed,
                "fee_lamports": verdict.sell.fee_lamports,
                "invoked_programs": verdict.sell.invoked_programs,
                "token_balance_deltas": [
                    {
                        "account_index": item.account_index,
                        "mint": item.mint,
                        "owner": item.owner,
                        "before": str(item.before),
                        "after": str(item.after),
                        "delta": str(item.delta),
                    }
                    for item in verdict.sell.token_balance_deltas
                ],
            }
            if verdict.sell is not None
            else None
        ),
    }

    print(json.dumps(output, indent=2))
    return 0 if verdict.sellable else 1


if __name__ == "__main__":
    raise SystemExit(main())
