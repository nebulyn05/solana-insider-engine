import logging
import sys

from app.intelligence.ancestry.engine import persist_ancestry, trace_ancestry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("ancestry")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/run_ancestry.py <wallet>")
        return 2

    wallet = sys.argv[1].strip()
    if not wallet:
        print("wallet must not be empty")
        return 2

    result = trace_ancestry(wallet)
    persisted = persist_ancestry(result)

    logger.info(
        "ancestry wallet=%s root=%s flagged=%s reason=%s hops=%d persisted=%d",
        result.wallet,
        result.root_wallet,
        result.root_classification.flagged,
        result.root_classification.reason,
        len(result.edges),
        persisted,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
