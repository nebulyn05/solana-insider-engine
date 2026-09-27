from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ExecutionConditions:
    liquidity_sol: Decimal
    notional_sol: Decimal
    volatility_bps: Decimal = Decimal("0")
    network_delay_ms: Decimal = Decimal("0")
    base_slippage_bps: Decimal = Decimal("300")
    latency_bps_per_100ms: Decimal = Decimal("20")

    def validate(self) -> None:
        if self.liquidity_sol <= 0 or self.notional_sol <= 0:
            raise ValueError("liquidity and notional must be positive")
        if self.volatility_bps < 0 or self.network_delay_ms < 0:
            raise ValueError("volatility and delay must be non-negative")
        if self.base_slippage_bps < 0:
            raise ValueError("base_slippage_bps must be non-negative")


@dataclass(frozen=True)
class SlippageEstimate:
    total_bps: Decimal
    liquidity_impact_bps: Decimal
    volatility_bps: Decimal
    latency_bps: Decimal
    execution_price: Decimal


def estimate_buy_price(
    requested_price: Decimal,
    conditions: ExecutionConditions,
) -> SlippageEstimate:
    conditions.validate()
    if requested_price <= 0:
        raise ValueError("requested_price must be positive")

    participation = conditions.notional_sol / conditions.liquidity_sol
    liquidity_impact = min(
        Decimal("5000"),
        participation * Decimal("10000"),
    )
    latency = (
        conditions.network_delay_ms / Decimal("100")
    ) * conditions.latency_bps_per_100ms
    total = (
        conditions.base_slippage_bps
        + liquidity_impact
        + conditions.volatility_bps
        + latency
    )
    price = requested_price * (Decimal("1") + total / Decimal("10000"))
    return SlippageEstimate(
        total_bps=total,
        liquidity_impact_bps=liquidity_impact,
        volatility_bps=conditions.volatility_bps,
        latency_bps=latency,
        execution_price=price,
    )
