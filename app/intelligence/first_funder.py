from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from app.intelligence.ancestry.engine import FundingEdge, MAX_ANCESTRY_HOPS, trace_ancestry


@dataclass(frozen=True)
class FirstFunderMatch:
    buyer_wallet: str
    deployer_wallet: str
    root_wallet: str
    root_is_deployer: bool
    deployer_in_lineage: bool
    lineage_id: UUID
    hops: int
    edges: tuple[FundingEdge, ...]


@dataclass(frozen=True)
class SharedFirstFunderResult:
    deployer_wallet: str
    matches: tuple[FirstFunderMatch, ...]

    @property
    def matched_buyers(self) -> tuple[FirstFunderMatch, ...]:
        return tuple(match for match in self.matches if match.root_is_deployer)

    @property
    def shared_first_funder(self) -> bool:
        return bool(self.matched_buyers)

    @property
    def lineage_hits(self) -> tuple[FirstFunderMatch, ...]:
        return tuple(
            match for match in self.matches if match.deployer_in_lineage
        )


def _match_buyer(
    buyer_wallet: str,
    deployer_wallet: str,
    max_hops: int,
) -> FirstFunderMatch:
    if not buyer_wallet:
        raise ValueError("buyer wallet must not be empty")
    if not deployer_wallet:
        raise ValueError("deployer wallet must not be empty")

    if buyer_wallet == deployer_wallet:
        return FirstFunderMatch(
            buyer_wallet=buyer_wallet,
            deployer_wallet=deployer_wallet,
            root_wallet=deployer_wallet,
            root_is_deployer=True,
            deployer_in_lineage=True,
            lineage_id=uuid4(),
            hops=0,
            edges=(),
        )

    result = trace_ancestry(buyer_wallet, max_hops=max_hops)
    lineage_wallets = {buyer_wallet}
    lineage_wallets.update(edge.source_wallet for edge in result.edges)

    return FirstFunderMatch(
        buyer_wallet=buyer_wallet,
        deployer_wallet=deployer_wallet,
        root_wallet=result.root_wallet,
        root_is_deployer=result.root_wallet == deployer_wallet,
        deployer_in_lineage=deployer_wallet in lineage_wallets,
        lineage_id=result.lineage_id,
        hops=len(result.edges),
        edges=result.edges,
    )


def check_shared_first_funder(
    buyer_wallets: list[str] | tuple[str, ...],
    deployer_wallet: str,
    max_hops: int = MAX_ANCESTRY_HOPS,
) -> SharedFirstFunderResult:
    """Compare buyer funding roots against a token deployer wallet.

    A buyer is a first-funder match only when the terminal wallet reached by
    the ancestry walk is the deployer. A separate lineage hit records cases
    where the deployer appears anywhere in the traversed ancestry, even when
    another wallet is the terminal root.

    No transaction is submitted by this module.
    """
    if not deployer:
        raise ValueError("deployer wallet must not be empty")
    if not 1 <= max_hops <= MAX_ANCESTRY_HOPS:
        raise ValueError(f"max_hops must be between 1 and {MAX_ANCESTRY_HOPS}")

    unique_buyers = tuple(dict.fromkeys(wallet.strip() for wallet in buyer_wallets))
    if not all(unique_buyers):
        raise ValueError("buyer wallets must not contain empty values")

    matches = tuple(
        _match_buyer(buyer, deployer, max_hops)
        for buyer in unique_buyers
    )
    return SharedFirstFunderResult(
        deployer_wallet=deployer,
        matches=matches,
    )
