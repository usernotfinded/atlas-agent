# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_order.py
# PURPOSE: Verifies order behavior and regression expectations.
# DEPS:    math, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import math

import pytest

from atlas_agent.execution.order import Order


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_order_notional_valid() -> None:
    order = Order(symbol="AAPL", side="buy", quantity=10, limit_price=150.0)
    assert order.notional == 1500.0


@pytest.mark.parametrize(
    "bad_quantity",
    ["abc", {}, [], object(), None],
)
def test_order_notional_rejects_non_numeric_quantity(bad_quantity) -> None:
    order = Order(symbol="AAPL", side="buy", quantity=bad_quantity, limit_price=150.0)
    with pytest.raises(ValueError, match="order quantity must be a positive finite number"):
        order.notional


@pytest.mark.parametrize(
    "bad_limit_price",
    ["abc", {}, [], object(), 0, -1, float("nan"), float("inf")],
)
def test_order_notional_rejects_invalid_limit_price(bad_limit_price) -> None:
    order = Order(symbol="AAPL", side="buy", quantity=10, limit_price=bad_limit_price)
    with pytest.raises(ValueError, match="Cannot evaluate notional for market order without reference price"):
        order.notional


@pytest.mark.parametrize("bad_quantity", [True, False])
def test_order_notional_rejects_boolean_quantity(bad_quantity) -> None:
    order = Order(symbol="AAPL", side="buy", quantity=bad_quantity, limit_price=150.0)
    with pytest.raises(ValueError, match="order quantity must be a positive finite number"):
        order.notional


@pytest.mark.parametrize("bad_limit_price", [True, False])
def test_order_notional_rejects_boolean_limit_price(bad_limit_price) -> None:
    order = Order(symbol="AAPL", side="buy", quantity=10, limit_price=bad_limit_price)
    with pytest.raises(ValueError, match="Cannot evaluate notional for market order without reference price"):
        order.notional
