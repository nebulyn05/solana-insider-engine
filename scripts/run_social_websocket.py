from __future__ import annotations

import argparse
import asyncio
import logging

from app.social.websocket import SocialSubscription, run_social_websocket


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Phase 4.1 social-media WebSocket ingestion interface."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--x-developer",
        action="append",
        default=[],
        help="X developer/source key; repeat for multiple accounts.",
    )
    parser.add_argument(
        "--telegram-group",
        action="append",
        default=[],
        help="Telegram group/channel source key; repeat for multiple groups.",
    )
    args = parser.parse_args()

    subscriptions = [
        SocialSubscription("x", key) for key in args.x_developer
    ] + [
        SocialSubscription("telegram", key) for key in args.telegram_group
    ]

    if not subscriptions:
        parser.error("at least one --x-developer or --telegram-group is required")

    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_social_websocket(args.host, args.port, subscriptions))


if __name__ == "__main__":
    main()
