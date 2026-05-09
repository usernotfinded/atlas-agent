from __future__ import annotations

import pytest
from atlas_agent.risk.manager import RiskManager
from atlas_agent.risk.models import PortfolioSnapshot, RiskPosition
from atlas_agent.safety.action_plan import SafetyActionPlanner
from atlas_agent.safety.models import KillSwitchDecision


@pytest.fixture
def planner():
    return SafetyActionPlanner(risk_manager=RiskManager())


@pytest.fixture
def empty_portfolio():
    return PortfolioSnapshot(cash=10000, equity=10000, total_exposure=0, positions=[])


def test_cancel_all_with_no_open_orders_returns_no_op(planner, empty_portfolio):
    decision = KillSwitchDecision(allowed=False, status="cancel_required", mode="cancel_all")
    plan = planner.create_plan(decision, empty_portfolio, open_order_ids=[])
    
    assert plan.status == "planned"
    assert len(plan.actions) == 1
    assert plan.actions[0].type == "no_op"


def test_cancel_all_with_open_orders_creates_cancel_actions(planner, empty_portfolio):
    decision = KillSwitchDecision(allowed=False, status="cancel_required", mode="cancel_all")
    plan = planner.create_plan(decision, empty_portfolio, open_order_ids=["ord_1", "ord_2"])
    
    assert plan.status == "requires_approval"
    assert len(plan.actions) == 2
    assert plan.actions[0].type == "cancel_order"
    assert plan.actions[0].params["order_id"] == "ord_1"


def test_flatten_all_with_no_positions_returns_no_op(planner, empty_portfolio):
    decision = KillSwitchDecision(allowed=False, status="flatten_required", mode="flatten_all")
    plan = planner.create_plan(decision, empty_portfolio, open_order_ids=[])
    
    assert plan.status == "planned"
    assert plan.actions[0].type == "no_op"


def test_flatten_all_with_long_position_creates_sell_action(planner):
    portfolio = PortfolioSnapshot(
        cash=5000, equity=10000, total_exposure=5000,
        positions=[RiskPosition(symbol="AAPL", quantity=10, average_price=500, market_price=500, notional=5000, side="long")]
    )
    decision = KillSwitchDecision(allowed=False, status="flatten_required", mode="flatten_all")
    plan = planner.create_plan(decision, portfolio, open_order_ids=[])
    
    assert plan.status == "requires_approval"
    assert len(plan.actions) == 1
    assert plan.actions[0].type == "flatten_position"
    assert plan.actions[0].params["side"] == "sell"


def test_flatten_all_with_short_position_creates_buy_action(planner):
    portfolio = PortfolioSnapshot(
        cash=15000, equity=10000, total_exposure=5000,
        positions=[RiskPosition(symbol="AAPL", quantity=-10, average_price=500, market_price=500, notional=5000, side="short")]
    )
    # RiskManager must allow shorting or at least allow reducing short
    decision = KillSwitchDecision(allowed=False, status="flatten_required", mode="flatten_all")
    plan = planner.create_plan(decision, portfolio, open_order_ids=[])
    
    assert plan.status == "requires_approval"
    assert len(plan.actions) == 1
    assert plan.actions[0].type == "flatten_position"
    assert plan.actions[0].params["side"] == "buy"


def test_locked_down_returns_blocked_plan(planner, empty_portfolio):
    decision = KillSwitchDecision(allowed=False, status="locked_down", mode="locked_down")
    plan = planner.create_plan(decision, empty_portfolio, open_order_ids=[])
    
    assert plan.status == "blocked"
    assert any(a.type == "notify_user" for a in plan.actions)
