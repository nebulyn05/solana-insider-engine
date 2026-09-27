from decimal import Decimal

from app.replay.monte_carlo import run_monte_carlo


def test_monte_carlo_is_reproducible() -> None:
    values = [Decimal("1"), Decimal("-0.5"), Decimal("0.25")]
    a = run_monte_carlo(values, runs=100, seed=11)
    b = run_monte_carlo(values, runs=100, seed=11)
    assert a == b
    assert a.runs == 100
