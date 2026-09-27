from __future__ import annotations

import argparse

from app.intelligence.wallet_features import refresh_wallet_features


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wallet")
    args = parser.parse_args()
    print(refresh_wallet_features(args.wallet))


if __name__ == "__main__":
    main()
