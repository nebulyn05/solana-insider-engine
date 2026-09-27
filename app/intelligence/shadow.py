from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Protocol


@dataclass(frozen=True)
class ShadowTokenModel:
    """Local execution model used without signing or broadcasting a transaction."""

    token_mint: str
    buy_price: Decimal
    liquidity_sol: Decimal
    buy_fee_bps: Decimal = Decimal("0")
    sell_fee_bps: Decimal = Decimal("0")
    sell_enabled: bool = True
    max_sell_fraction: Decimal = Decimal("1")


@dataclass(frozen=True)
class ShadowLeg:
    side: str
    input_amount: Decimal
    output_amount: Decimal
    price: Decimal
    fee: Decimal


@dataclass(frozen=True)
class ShadowSimulation:
    token_mint: str
    buy: ShadowLeg
    sell: ShadowLeg | None
    sellable: bool
    round_trip_pnl_sol: Decimal
    round_trip_return_bps: Decimal
    rejection_reason: str | None


class ShadowExecutionAdapter(Protocol):
    def simulate(self, model: ShadowTokenModel, notional_sol: Decimal) -> ShadowSimulation:
        ...


class LocalShadowSimulator:
    """Deterministic buy->sell interceptor.

    This never creates a Solana transaction, invokes a program, signs a message,
    or broadcasts anything. It models execution mechanics locally so the paper
    engine can reject a token before creating a simulated position.
    """

    def __init__(self, adapter: ShadowExecutionAdapter | None = None) -> None:
        self._adapter = adapter or DeterministicShadowAdapter()

    def run(self, model: ShadowTokenModel, notional_sol: Decimal) -> ShadowSimulation:
        if not model.token_mint:
            raise ValueError("token_mint is required")
        if model.buy_price <= 0:
            raise ValueError("buy_price must be positive")
        if model.liquidity_sol <= 0:
            raise ValueError("liquidity_sol must be positive")
        if notional_sol <= 0:
            raise ValueError("notional_sol must be positive")
        if not Decimal("0") <= model.buy_fee_bps <= Decimal("10000"):
            raise ValueError("buy_fee_bps must be between 0 and 10000")
        if not Decimal("0") <= model.sell_fee_bps <= Decimal("10000"):
            raise ValueError("sell_fee_bps must be between 0 and 10000")
        if not Decimal("0") < model.max_sell_fraction <= Decimal("1"):
            raise ValueError("max_sell_fraction must be > 0 and <= 1")

        return self._adapter.simulate(model, notional_sol)


class DeterministicShadowAdapter:
    """Simple local AMM-like model for simulation and unit testing."""

    _SCALE = Decimal("0.000000000000000001")

    @classmethod
    def _quantize(cls, value: Decimal) -> Decimal:
        return value.quantize(cls._SCALE, rounding=ROUND_DOWN)

    def simulate(self, model: ShadowTokenModel, notional_sol: Decimal) -> ShadowSimulation:
        buy_fee = notional_sol * model.buy_fee_bps / Decimal("10000")
        net_buy = notional_sol - buy_fee
        token_quantity = net_buy / model.buy_price

        buy = ShadowLeg(
            side="BUY",
            input_amount=notional_sol,
            output_amount=self._quantize(token_quantity),
            price=model.buy_price,
            fee=self._quantize(buy_fee),
        )

        if not model.sell_enabled:
            return ShadowSimulation(
                token_mint=model.token_mint,
                buy=buy,
                sell=None,
                sellable=False,
                round_trip_pnl_sol=Decimal("-") + notional_sol,
                round_trip_return_bps=Decimal("-10000"),
                rejection_reason="sell_disabled",
            )

        sellable_quantity = token_quantity * model.max_sell_fraction
        gross_sell = sellable_quantity * model.buy_price
        sell_fee = gross_sell * model.sell_fee_bps / Decimal("10000")
        net_sell = gross_sell - sell_fee

        if net_sell > model.liquidity_sol:
            return ShadowSimulation(
                token_mint=model.token_mint,
                buy=buy,
                sell=None,
                sellable=False,
                round_trip_pnl_sol=Decimal("-") + notional_sol,
                round_trip_return_bps=Decimal("-10000"),
                rejection_reason="insufficient_shadow_liquidity",
            )

        sell = ShadowLeg(
            side="SELL",
            input_amount=self._quantize(sellable_quantity),
            output_amount=self._quantize(net_sell),
            price=model.buy_price,
            fee=self._quantize(sell_fee),
        )
        pnl = net_sell - notional_sol
        return ShadowSimulation(
            token_mint=model.token_mint,
            buy=buy,
            sell=sell,
            sellable=True,
            round_trip_pnl_sol=self._quantize(pnl),
            round_trip_return_bps=self._quantize(
                (pnl / notional_sol) * Decimal("10000")
            ),
            rejection_reason=None,
        )
