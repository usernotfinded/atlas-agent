# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/risk/test_risk_manager_v2.py
# PURPOSE: Verifies risk manager v2 behavior and regression expectations.
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
def portfolio():
    return PortfolioSnapshot(
        cash=10000.0,
        equity=10000.0,
        total_exposure=0.0,
        positions=[]
    )


def test_risk_manager_allows_valid_paper_trade(portfolio):
    limits = RiskLimits(max_single_trade_notional=1000.0)
    manager = RiskManager(limits=limits)
    
    order = OrderRiskInput(
        symbol="AAPL",
        side="buy",
        quantity=10,
        price=150.0,
        notional=1500.0 # Wait, 1500 > 1000
    )
    # Correcting: 10 * 150 = 1500
    
    order = OrderRiskInput(
        symbol="AAPL",
        side="buy",
        quantity=5,
        price=150.0,
        notional=750.0
    )
    
    decision = manager.evaluate_order(order, portfolio, mode="paper")
    assert decision.allowed is True
    assert decision.status == "allowed"


def test_risk_manager_blocks_large_trade(portfolio):
    limits = RiskLimits(max_single_trade_notional=1000.0)
    manager = RiskManager(limits=limits)
    
    order = OrderRiskInput(
        symbol="AAPL",
        side="buy",
        quantity=10,
        price=150.0,
        notional=1500.0
    )
    
    decision = manager.evaluate_order(order, portfolio, mode="paper")
    assert decision.allowed is False
    assert decision.status == "blocked"
    assert any(v.rule == "max_single_trade_notional" for v in decision.violations)


def test_risk_manager_enforces_blocked_symbols(portfolio):
    limits = RiskLimits(blocked_symbols={"TSLA"})
    manager = RiskManager(limits=limits)
    
    order = OrderRiskInput(
        symbol="TSLA",
        side="buy",
        quantity=1,
        price=200.0,
        notional=200.0
    )
    
    decision = manager.evaluate_order(order, portfolio, mode="paper")
    assert decision.allowed is False
    assert any(v.rule == "blocked_symbols" for v in decision.violations)


def test_risk_manager_enforces_allowed_symbols(portfolio):
    limits = RiskLimits(allowed_symbols={"AAPL", "MSFT"})
    manager = RiskManager(limits=limits)
    
    order = OrderRiskInput(
        symbol="GOOG",
        side="buy",
        quantity=1,
        price=100.0,
        notional=100.0
    )
    
    decision = manager.evaluate_order(order, portfolio, mode="paper")
    assert decision.allowed is False
    assert any(v.rule == "allowed_symbols" for v in decision.violations)


def test_risk_manager_blocks_live_unless_enabled(portfolio):
    limits = RiskLimits(paper_only=True)
    manager = RiskManager(limits=limits)
    
    order = OrderRiskInput(
        symbol="AAPL",
        side="buy",
        quantity=1,
        price=150.0,
        notional=150.0
    )
    
    decision = manager.evaluate_order(order, portfolio, mode="live")
    assert decision.allowed is False
    assert any(v.rule == "paper_only" for v in decision.violations)


def test_risk_manager_requires_stop_loss_in_live(portfolio):
    limits = RiskLimits(paper_only=False, live_trading_enabled=True, require_stop_loss_live=True)
    manager = RiskManager(limits=limits)
    
    order = OrderRiskInput(
        symbol="AAPL",
        side="buy",
        quantity=1,
        price=150.0,
        notional=150.0,
        stop_loss=None
    )
    
    decision = manager.evaluate_order(order, portfolio, mode="live")
    assert decision.allowed is False
    assert any(v.rule == "require_stop_loss_live" for v in decision.violations)
