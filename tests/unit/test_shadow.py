from decimal import Decimal

from app.intelligence.shadow import LocalShadowSimulator, ShadowTokenModel


def model(**overrides):
    values = {
        "token_mint": "mint",
        "buy_price": Decimal("2"),
        "liquidity_sol": Decimal("100"),
    }
    values.update(overrides)
    return ShadowTokenModel(**values)


def test_shadow_buy_sell_is_sellable() -> None:
    result = LocalShadowSimulator().run(model(), Decimal("1"))
    assert result.sellable is True
    assert result.sell is not None
    assert result.round_trip_pnl_sol == Decimal("0")


def test_shadow_rejects_disabled_sell() -> None:
    result = LocalShadowSimulator().run(model(sell_enabled=False), Decimal("1"))
    assert result.sellable is False
    assert result.rejection_reason == "sell_disabled"
    assert result.round_trip_pnl_sol == Decimal("-1")


def test_shadow_models_sell_tax() -> None:
    result = LocalShadowSimulator().run(model(sell_fee_bps=Decimal("500")), Decimal("1"))
    assert result.sellable is True
    assert result.round_trip_pnl_sol < Decimal("0")
    assert result.round_trip_return_bps == Decimal("-500")


def test_shadow_rejects_excessive_sell() -> None:
    result = LocalShadowSimulator().run(
        model(max_sell_fraction=Decimal("1"), liquidity_sol=Decimal("0.05")),
        Decimal("1"),
    )
    assert result.sellable is False
    assert result.sell is None
    assert result.rejection_reason == "insufficient_shadow_liquidity"
    assert result.round_trip_pnl_sol == Decimal("-1")
