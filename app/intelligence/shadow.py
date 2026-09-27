from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Protocol


@dataclass(frozen=True)
class ShadowTokenModel:
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
    """Pure local simulator: no signing, transaction creation or broadcasting."""

    def __init__(self, adapter: ShadowExecutionAdapter | None = None) -> None:
        self._adapter = adapter or DeterministicShadowAdapter()

    def run(self, model: ShadowTokenModel, notional_sol: Decimal) -> ShadowSimulation:
        if not model.token_mint:
            raise ValueError("token_mint is required")
        if model.buy_price <= 0 or model.liquidity_sol <= 0 or notional_sol <= 0:
            raise ValueError("price, liquidity and notional must be positive")
        if not Decimal("0") <= model.buy_fee_bps <= Decimal("10000"):
            raise ValueError("buy_fee_bps must be between 0 and 10000")
        if not Decimal("0") <= model.sell_fee_bps <= Decimal("10000"):
            raise ValueError("sell_fee_bps must be between 0 and 10000")
        if not Decimal("0") < model.max_sell_fraction <= Decimal("1"):
            raise ValueError("max_sell_fraction must be > 0 and <= 1")
        return self._adapter.simulate(model, notional_sol)


class DeterministicShadowAdapter:
    _SCALE = Decimal("0.000000000000000001")

    @classmethod
    def _q(cls, value: Decimal) -> Decimal:
        return value.quantize(cls._SCALE, rounding=ROUND_DOWN)

    def simulate(self, model: ShadowTokenModel, notional_sol: Decimal) -> ShadowSimulation:
        buy_fee = notional_sol * model.buy_fee_bps / Decimal("10000")
        net_buy = notional_sol - buy_fee
        token_quantity = net_buy / model.buy_price
        buy = ShadowLeg("BUY", notional_sol, self._q(token_quantity), model.buy_price, self._q(buy_fee))

        if not model.sell_enabled:
            return ShadowSimulation(
                model.token_mint, buy, None, False, -notional_sol,
                Decimal("-10000"), "sell_disabled"
            )

        sellable_quantity = token_quantity * model.max_sell_fraction
        gross_sell = sellable_quantity * model.buy_price
        sell_fee = gross_sell * model.sell_fee_bps / Decimal("10000")
        net_sell = gross_sell - sell_fee

        if net_sell > model.liquidity_sol:
            return ShadowSimulation(
                model.token_mint, buy, None, False, -notional_sol,
                Decimal("-10000"), "insufficient_shadow_liquidity"
            )

        sell = ShadowLeg("SELL", self._q(sellable_quantity), self._q(net_sell), model.buy_price, self._q(sell_fee))
        pnl = net_sell - notional_sol
        return ShadowSimulation(
            model.token_mint, buy, sell, True, self._q(pnl),
            self._q((pnl / notional_sol) * Decimal("10000")), None
        )
