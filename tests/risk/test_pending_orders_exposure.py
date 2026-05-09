from __future__ import annotations

import pytest
from atlas_agent.risk.manager import RiskManager
from atlas_agent.risk.limits import RiskLimits
from atlas_agent.risk.models import OrderRiskInput, PortfolioSnapshot, RiskPosition, PendingOrder


@pytest.fixture
def empty_portfolio():
    return PortfolioSnapshot(
        cash=10000.0,
        equity=10000.0,
        total_exposure=0.0,
        positions=[],
        open_orders=[]
    )


def test_pending_buy_increases_projected_long_exposure(empty_portfolio):
    # Setup: 1 existing pending buy for 5 units at 100
    empty_portfolio.open_orders.append(
        PendingOrder(order_id="p1", symbol="AAPL", side="buy", quantity=5, limit_price=100.0, status="open")
    )
    
    manager = RiskManager()
    # Propose buy another 5 units at 100
    order = OrderRiskInput(symbol="AAPL", side="buy", quantity=5, price=100.0, notional=500.0)
    
    decision = manager.evaluate_order(order, empty_portfolio)
    
    assert decision.projected_quantity == 5.0 # Just current + proposed
    assert decision.projected_quantity_with_pending == 10.0 # Current + pending + proposed
    assert decision.projected_exposure_with_pending == 1000.0
    assert "p1" in decision.diagnostics["included_pending_order_ids"]


def test_pending_sell_reduces_projected_long_exposure():
    # Setup: Current position 10 long. Pending sell 4.
    portfolio = PortfolioSnapshot(
        cash=9000.0, equity=10000.0, total_exposure=1000.0,
        positions=[RiskPosition(symbol="AAPL", quantity=10, average_price=100, market_price=100, notional=1000, side="long")],
        open_orders=[PendingOrder(order_id="p1", symbol="AAPL", side="sell", quantity=4, status="open")]
    )
    
    manager = RiskManager()
    # Propose selling 2 more
    order = OrderRiskInput(symbol="AAPL", side="sell", quantity=2, price=100.0, notional=200.0)
    
    decision = manager.evaluate_order(order, portfolio)
    
    assert decision.projected_quantity == 8.0 # 10 - 2
    assert decision.projected_quantity_with_pending == 4.0 # 10 - 4 - 2
    assert decision.projected_exposure_with_pending == 400.0


def test_pending_sell_flips_short_and_blocked_if_no_shorting():
    # Setup: Long 5. Pending sell 10. (Projected -5)
    portfolio = PortfolioSnapshot(
        cash=9500.0, equity=10000.0, total_exposure=500.0,
        positions=[RiskPosition(symbol="AAPL", quantity=5, average_price=100, market_price=100, notional=500, side="long")],
        open_orders=[PendingOrder(order_id="p1", symbol="AAPL", side="sell", quantity=10, status="open")]
    )
    
    # Propose selling 1 more (Projected -6)
    order = OrderRiskInput(symbol="AAPL", side="sell", quantity=1, price=100.0, notional=100.0)
    
    limits = RiskLimits(allow_shorting=False)
    manager = RiskManager(limits=limits)
    
    decision = manager.evaluate_order(order, portfolio)
    
    assert decision.allowed is False
    assert any(v.rule == "allow_shorting" for v in decision.violations)


def test_inactive_orders_are_ignored(empty_portfolio):
    # Setup: various non-active statuses
    empty_portfolio.open_orders = [
        PendingOrder(order_id="c1", symbol="AAPL", side="buy", quantity=10, status="cancelled"),
        PendingOrder(order_id="f1", symbol="AAPL", side="buy", quantity=10, status="filled"),
        PendingOrder(order_id="r1", symbol="AAPL", side="buy", quantity=10, status="rejected"),
    ]
    
    manager = RiskManager()
    order = OrderRiskInput(symbol="AAPL", side="buy", quantity=5, price=100.0, notional=500.0)
    
    decision = manager.evaluate_order(order, empty_portfolio)
    assert decision.projected_quantity_with_pending == 5.0
    assert len(decision.diagnostics["included_pending_order_ids"]) == 0
    assert len(decision.diagnostics["ignored_pending_order_ids"]) == 3


def test_partially_filled_order_counts_remaining_quantity(empty_portfolio):
    # Setup: 10 units total, 3 already filled. Remaining 7.
    empty_portfolio.open_orders.append(
        PendingOrder(order_id="pf1", symbol="AAPL", side="buy", quantity=10, filled_quantity=3, status="partially_filled")
    )
    
    manager = RiskManager()
    order = OrderRiskInput(symbol="AAPL", side="buy", quantity=1, price=100.0, notional=100.0)
    
    decision = manager.evaluate_order(order, empty_portfolio)
    assert decision.projected_quantity_with_pending == 8.0 # 7 + 1


def test_proposed_buy_blocked_when_pending_reaches_limit(empty_portfolio):
    # Limit: 1000. Pending buy: 900.
    empty_portfolio.open_orders.append(
        PendingOrder(order_id="p1", symbol="AAPL", side="buy", quantity=9, limit_price=100.0, status="open")
    )
    
    limits = RiskLimits(max_position_notional=1000.0)
    manager = RiskManager(limits=limits)
    
    # Propose buy 2 (200). 900 + 200 = 1100 > 1000.
    order = OrderRiskInput(symbol="AAPL", side="buy", quantity=2, price=100.0, notional=200.0)
    
    decision = manager.evaluate_order(order, empty_portfolio)
    assert decision.allowed is False
    assert any(v.rule == "max_position_notional" for v in decision.violations)


def test_risk_reducing_order_allowed_even_if_pending_exposure_high():
    # Limit: 1000. Long 10 (1000). Pending buy 10 (1000). 
    # Total projected exposure: 2000 > 1000.
    portfolio = PortfolioSnapshot(
        cash=8000.0, equity=10000.0, total_exposure=1000.0,
        positions=[RiskPosition(symbol="AAPL", quantity=10, average_price=100, market_price=100, notional=1000, side="long")],
        open_orders=[PendingOrder(order_id="p1", symbol="AAPL", side="buy", quantity=10, status="open")]
    )
    
    limits = RiskLimits(max_position_notional=1000.0)
    manager = RiskManager(limits=limits)
    
    # Propose SELLING 5. This reduces risk relative to current position.
    order = OrderRiskInput(symbol="AAPL", side="sell", quantity=5, price=100.0, notional=500.0)
    
    decision = manager.evaluate_order(order, portfolio)
    # Even though projected_with_pending is 1500 > 1000, 
    # the proposed trade itself is risk-reducing (reduces_risk classification).
    assert decision.allowed is True
    assert decision.classification == "reduces_risk"


def test_max_open_positions_includes_pending_new_symbols(empty_portfolio):
    # Max positions: 2.
    # Current positions: 1 (AAPL). 
    # Pending order for new symbol: 1 (MSFT).
    # Total effective symbols: 2.
    empty_portfolio.positions = [RiskPosition(symbol="AAPL", quantity=1, average_price=100, market_price=100, notional=100, side="long")]
    empty_portfolio.open_orders = [PendingOrder(order_id="p1", symbol="MSFT", side="buy", quantity=1, status="open")]
    
    limits = RiskLimits(max_open_positions=2)
    manager = RiskManager(limits=limits)
    
    # Propose buy GOOG (3rd symbol)
    order = OrderRiskInput(symbol="GOOG", side="buy", quantity=1, price=100.0, notional=100.0)
    
    decision = manager.evaluate_order(order, empty_portfolio)
    assert decision.allowed is False
    assert any(v.rule == "max_open_positions" for v in decision.violations)
