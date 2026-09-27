from decimal import Decimal

import pytest

from app.execution.lifecycle import _outcome
from app.execution.slippage import ExecutionConditions, estimate_buy_price


def test_outcome_is_price_directional() -> None:
    assert _outcome(Decimal("2"), Decimal("1")) == "WIN"
    assert _outcome(Decimal("1"), Decimal("2")) == "LOSS"


def test_slippage_increases_with_participation() -> None:
    small = estimate_buy_price(
        Decimal("1"),
        ExecutionConditions(liquidity_sol=Decimal("100"), notional_sol=Decimal("1")),
    )
    large = estimate_buy_price(
        Decimal("1"),
        ExecutionConditions(liquidity_sol=Decimal("100"), notional_sol=Decimal("10")),
    )
    assert large.total_bps > small.total_bps
    assert large.execution_price > small.execution_price


def test_latency_adds_slippage() -> None:
    base = estimate_buy_price(
        Decimal("1"),
        ExecutionConditions(liquidity_sol=Decimal("100"), notional_sol=Decimal("1")),
    )
    delayed = estimate_buy_price(
        Decimal("1"),
        ExecutionConditions(
            liquidity_sol=Decimal("100"),
            notional_sol=Decimal("1"),
            network_delay_ms=Decimal("500"),
        ),
    )
    assert delayed.total_bps > base.total_bps
