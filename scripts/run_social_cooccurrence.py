from __future__ import annotations

import argparse

from app.intelligence.social_cooccurrence import SocialCoOccurrenceFilter


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply the 1-10 minute social co-occurrence confidence upgrade."
    )
    parser.add_argument("buy_event_id", type=int, nargs="?")
    parser.add_argument("--pending", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    filter_ = SocialCoOccurrenceFilter()
    if args.pending:
        confirmations = filter_.evaluate_pending(args.limit)
        for confirmation in confirmations:
            print(confirmation)
        return

    if args.buy_event_id is None:
        parser.error("provide buy_event_id or --pending")

    confirmation = filter_.evaluate_buy_event(args.buy_event_id)
    print(confirmation if confirmation else "no_match")


if __name__ == "__main__":
    main()
