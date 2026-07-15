# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/risk/test_projected_exposure.py
# PURPOSE: Verifies projected exposure behavior and regression expectations.
# DEPS:    pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import pytest
from atlas_agent.risk.manager import RiskManager
from atlas_agent.risk.limits import RiskLimits
from atlas_agent.risk.models import OrderRiskInput, PortfolioSnapshot, RiskPosition


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

@pytest.fixture
def empty_portfolio():
    return PortfolioSnapshot(
        cash=10000.0,
        equity=10000.0,
        total_exposure=0.0,
        positions=[]
    )


def test_buy_on_flat_position_opens_long(empty_portfolio):
    limits = RiskLimits(max_single_trade_notional=10000.0, max_position_notional=10000.0)
    manager = RiskManager(limits=limits)
    order = OrderRiskInput(symbol="AAPL", side="buy", quantity=10, price=150.0, notional=1500.0)
    
    decision = manager.evaluate_order(order, empty_portfolio)
    
    assert decision.allowed is True
    assert decision.classification == "opens_new_position"
    assert decision.projected_quantity == 10.0
    assert decision.projected_exposure == 1500.0


def test_sell_on_long_position_reduces_risk():
    portfolio = PortfolioSnapshot(
        cash=8500.0, equity=10000.0, total_exposure=1500.0,
        positions=[RiskPosition(symbol="AAPL", quantity=10, average_price=150.0, market_price=150.0, notional=1500.0, side="long")]
    )
    # Even if limit is low, reducing risk should be allowed
    limits = RiskLimits(max_position_notional=100.0)
    manager = RiskManager(limits=limits)
    
    order = OrderRiskInput(symbol="AAPL", side="sell", quantity=5, price=150.0, notional=750.0)
    decision = manager.evaluate_order(order, portfolio)
    
    assert decision.allowed is True
    assert decision.classification == "reduces_risk"
    assert decision.projected_quantity == 5.0
    assert decision.projected_exposure == 750.0


def test_sell_on_long_position_closes_position():
    portfolio = PortfolioSnapshot(
        cash=8500.0, equity=10000.0, total_exposure=1500.0,
        positions=[RiskPosition(symbol="AAPL", quantity=10, average_price=150.0, market_price=150.0, notional=1500.0, side="long")]
    )
    manager = RiskManager()
    order = OrderRiskInput(symbol="AAPL", side="sell", quantity=10, price=150.0, notional=1500.0)
    
    decision = manager.evaluate_order(order, portfolio)
    
    assert decision.allowed is True
    assert decision.classification == "closes_position"
    assert decision.projected_quantity == 0.0
    assert decision.projected_exposure == 0.0


def test_flip_to_short_blocked_by_default():
    portfolio = PortfolioSnapshot(
        cash=9000.0, equity=10000.0, total_exposure=1500.0,
        positions=[RiskPosition(symbol="AAPL", quantity=10, average_price=150.0, market_price=150.0, notional=1500.0, side="long")]
    )
    limits = RiskLimits(allow_shorting=False)
    manager = RiskManager(limits=limits)
    
    # Sell 15 when holding 10 -> would result in -5
    order = OrderRiskInput(symbol="AAPL", side="sell", quantity=15, price=150.0, notional=2250.0)
    decision = manager.evaluate_order(order, portfolio)
    
    assert decision.allowed is False
    assert decision.classification == "flips_position"
    assert any(v.rule == "allow_shorting" for v in decision.violations)


def test_sell_on_flat_blocked_by_default(empty_portfolio):
    limits = RiskLimits(allow_shorting=False)
    manager = RiskManager(limits=limits)
    
    order = OrderRiskInput(symbol="AAPL", side="sell", quantity=5, price=150.0, notional=750.0)
    decision = manager.evaluate_order(order, empty_portfolio)
    
    assert decision.allowed is False
    assert any(v.rule == "allow_shorting" for v in decision.violations)


def test_buy_on_short_reduces_risk():
    portfolio = PortfolioSnapshot(
        cash=11500.0, equity=10000.0, total_exposure=1500.0,
        positions=[RiskPosition(symbol="AAPL", quantity=-10, average_price=150.0, market_price=150.0, notional=1500.0, side="short")]
    )
    limits = RiskLimits(max_position_notional=100.0, allow_shorting=False)
    manager = RiskManager(limits=limits)
    
    # Buy 5 to cover part of short
    order = OrderRiskInput(symbol="AAPL", side="buy", quantity=5, price=150.0, notional=750.0)
    decision = manager.evaluate_order(order, portfolio)
    
    assert decision.allowed is True
    assert decision.classification == "reduces_risk"
    assert decision.projected_quantity == -5.0


def test_buy_more_than_short_flips_long_correctly():
    portfolio = PortfolioSnapshot(
        cash=11500.0, equity=10000.0, total_exposure=1500.0,
        positions=[RiskPosition(symbol="AAPL", quantity=-10, average_price=150.0, market_price=150.0, notional=1500.0, side="short")]
    )
    limits = RiskLimits(max_single_trade_notional=10000.0, max_position_notional=10000.0)
    manager = RiskManager(limits=limits)
    
    # Buy 15 to flip from -10 to +5
    order = OrderRiskInput(symbol="AAPL", side="buy", quantity=15, price=150.0, notional=2250.0)
    decision = manager.evaluate_order(order, portfolio)
    
    assert decision.allowed is True
    assert decision.classification == "flips_position"
    assert decision.projected_quantity == 5.0


def test_max_open_positions_ignores_reductions():
    portfolio = PortfolioSnapshot(
        cash=5000.0, equity=10000.0, total_exposure=5000.0,
        positions=[
            RiskPosition(symbol=f"S{i}", quantity=1, average_price=100.0, market_price=100.0, notional=100.0, side="long")
            for i in range(10)
        ]
    )
    limits = RiskLimits(max_open_positions=10)
    manager = RiskManager(limits=limits)
    
    # Try to open 11th position -> blocked
    order1 = OrderRiskInput(symbol="NEW", side="buy", quantity=1, price=100.0, notional=100.0)
    assert manager.evaluate_order(order1, portfolio).allowed is False
    
    # Try to reduce existing S0 -> allowed
    order2 = OrderRiskInput(symbol="S0", side="sell", quantity=0.5, price=100.0, notional=50.0)
    assert manager.evaluate_order(order2, portfolio).allowed is True
