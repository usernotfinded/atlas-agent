"""Contract tests for risk.position_sizing.fixed_notional_quantity.

The function is the single place where notional -> quantity happens. Its docstring
promises that inputs which are not strictly positive raise ValueError. NaN and inf
must therefore raise too — a non-finite value that slips through would return a NaN or
inf quantity, the exact hazard order_router and RiskManager reject at their own doors
(a NaN quantity passes every downstream comparison unchanged).
"""

import math

import pytest

from atlas_agent.risk.position_sizing import fixed_notional_quantity


def test_returns_notional_divided_by_price() -> None:
    assert fixed_notional_quantity(1000.0, 250.0) == 4.0


def test_allows_fractional_quantity() -> None:
    assert fixed_notional_quantity(100.0, 3.0) == pytest.approx(33.3333333, rel=1e-6)


@pytest.mark.parametrize("notional", [0.0, -1.0, -0.0001])
def test_rejects_non_positive_notional(notional: float) -> None:
    with pytest.raises(ValueError):
        fixed_notional_quantity(notional, 100.0)


@pytest.mark.parametrize("price", [0.0, -1.0, -0.0001])
def test_rejects_non_positive_price(price: float) -> None:
    with pytest.raises(ValueError):
        fixed_notional_quantity(100.0, price)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_rejects_non_finite_notional(bad: float) -> None:
    # nan <= 0 is False and inf <= 0 is False, so the positivity guard alone lets these
    # through and returns a non-finite (or nonsensical) quantity.
    with pytest.raises(ValueError):
        fixed_notional_quantity(bad, 100.0)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_rejects_non_finite_price(bad: float) -> None:
    with pytest.raises(ValueError):
        fixed_notional_quantity(100.0, bad)
