import logging
import sys

from app.intelligence.first_funder import check_shared_first_funder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("first-funder")


def main() -> int:
    if len(sys.argv) < 3:
        print(
            "Usage: python scripts/run_first_funder.py "
            "<deployer_wallet> <buyer_wallet> [buyer_wallet ...]"
        )
        return 2

    deployer = sys.argv[1].strip()
    buyers = [wallet.strip() for wallet in sys.argv[2:]]

    result = check_shared_first_funder(buyers, deployer)

    for match in result.matches:
        logger.info(
            "buyer=%s root=%s root_is_deployer=%s deployer_in_lineage=%s hops=%d",
            match.buyer_wallet,
            match.root_wallet,
            match.root_is_deployer,
            match.deployer_in_lineage,
            match.hops,
        )

    logger.info(
        "deployer=%s buyers=%d first_funder_matches=%d lineage_hits=%d",
        deployer,
        len(result.matches),
        len(result.matched_buyers),
        len(result.lineage_hits),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
