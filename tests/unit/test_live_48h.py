from decimal import Decimal

import pytest

from app.simulation.live_48h import SimulationConfig


def test_default_simulation_config_uses_four_percent_penalty() -> None:
    config = SimulationConfig()
    config.validate()
    assert config.slippage_percent == Decimal("4.0")
    assert config.duration_hours == Decimal("48")


@pytest.mark.parametrize("value", [Decimal("2.99"), Decimal("5.01")])
def test_slippage_must_stay_within_three_to_five_percent(value: Decimal) -> None:
    with pytest.raises(ValueError, match="between 3 and 5"):
        SimulationConfig(slippage_percent=value).validate()


def test_custom_fixed_penalty_is_allowed() -> None:
    config = SimulationConfig(slippage_percent=Decimal("3.5"))
    config.validate()
    assert config.slippage_percent == Decimal("3.5")
