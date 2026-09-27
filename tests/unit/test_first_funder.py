from unittest.mock import patch

from app.intelligence.first_funder import (
    FirstFunderMatch,
    SharedFirstFunderResult,
    check_shared_first_funder,
)
from app.intelligence.ancestry.engine import AncestryResult, FundingEdge, RootClassification
from uuid import uuid4


def _result(buyer: str, root: str, *sources: str) -> AncestryResult:
    previous = buyer
    edges = []
    for index, source in enumerate(sources, start=1):
        edges.append(
            FundingEdge(
                signature=f"sig-{index}",
                slot=100 - index,
                source_wallet=source,
                destination_wallet=previous,
                amount_sol=1,
            )
        )
        previous = source

    return AncestryResult(
        wallet=buyer,
        lineage_id=uuid4(),
        edges=tuple(edges),
        root_wallet=root,
        root_classification=RootClassification(
            wallet=root,
            flagged=False,
            reason=None,
            label=None,
        ),
        max_hops_reached=False,
    )


def test_shared_first_funder_matches_terminal_deployer() -> None:
    mocked = _result("buyer-a", "deployer", "deployer")

    with patch(
        "app.intelligence.first_funder.trace_ancestry",
        return_value=mocked,
    ):
        result = check_shared_first_funder(["buyer-a"], "deployer")

    assert result.shared_first_funder is True
    assert len(result.matched_buyers) == 1
    assert result.matched_buyers[0].root_is_deployer is True
    assert result.matched_buyers[0].deployer_in_lineage is True


def test_lineage_hit_is_not_promoted_to_first_funder_match() -> None:
    mocked = _result("buyer-a", "funding-root", "deployer", "funding-root")

    with patch(
        "app.intelligence.first_funder.trace_ancestry",
        return_value=mocked,
    ):
        result = check_shared_first_funder(["buyer-a"], "deployer")

    assert result.shared_first_funder is False
    assert len(result.lineage_hits) == 1
    assert result.lineage_hits[0].root_is_deployer is False
    assert result.lineage_hits[0].deployer_in_lineage is True


def test_duplicate_buyers_are_evaluated_once() -> None:
    mocked = _result("buyer-a", "deployer", "deployer")

    with patch(
        "app.intelligence.first_funder.trace_ancestry",
        return_value=mocked,
    ) as trace:
        result = check_shared_first_funder(
            ["buyer-a", "buyer-a"],
            "deployer",
        )

    assert len(result.matches) == 1
    trace.assert_called_once_with("buyer-a", max_hops=5)
