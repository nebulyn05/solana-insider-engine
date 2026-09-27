import logging
import sys
from datetime import datetime, timezone
from decimal import Decimal

from app.intelligence.clustering import evaluate_and_paper_trade

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("clustering")


def main() -> int:
    if len(sys.argv) not in (3, 4):
        print(
            "Usage: python scripts/run_clustering.py "
            "<token_mint> <anchor_iso8601> [min_warm_wallets]"
        )
        return 2

    token_mint = sys.argv[1].strip()
    anchor = datetime.fromisoformat(sys.argv[2].replace("Z", "+00:00"))
    threshold = int(sys.argv[3]) if len(sys.argv) == 4 else 3

    result = evaluate_and_paper_trade(
        token_mint=token_mint,
        anchor_time=anchor.astimezone(timezone.utc),
        min_warm_wallets=threshold,
        window_seconds=30,
        notional_sol=Decimal("1"),
    )

    if result is None:
        logger.info("no qualifying warm-wallet cluster token=%s", token_mint)
        return 0

    logger.info(
        "paper trade created trade_id=%s token=%s wallets=%d signal=%s",
        result.trade_id,
        result.signal.token_mint,
        result.signal.event_count,
        result.signal.signal_id,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
