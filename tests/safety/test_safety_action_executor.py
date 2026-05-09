from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from atlas_agent.audit import AuditWriter
from atlas_agent.core.types import Session
from atlas_agent.risk.manager import RiskManager
from atlas_agent.risk.models import PortfolioSnapshot, RiskPosition
from atlas_agent.safety.executor import SafetyActionExecutor
from atlas_agent.safety.kill_switch import AdvancedKillSwitch
from atlas_agent.safety.models import SafetyAction, SafetyActionPlan, KillSwitchDecision
from atlas_agent.tools.registry import ToolRegistry
from atlas_agent.tools.spec import ToolSpec, ToolResult, ToolError


@pytest.fixture
def registry():
    reg = ToolRegistry()
    
    def cancel_order(order_id: str):
        return f"cancelled {order_id}"
    
    reg.register(ToolSpec(
        name="cancel_order",
        description_full="test",
        description_compact="test",
        input_schema={"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
        execute=cancel_order
    ))
    
    def flatten_position(symbol: str, side: str, quantity: float):
        return f"flattened {symbol}"
        
    reg.register(ToolSpec(
        name="flatten_position",
        description_full="test",
        description_compact="test",
        input_schema={
            "type": "object", 
            "properties": {
                "symbol": {"type": "string"},
                "side": {"type": "string"},
                "quantity": {"type": "number"}
            },
            "required": ["symbol", "side", "quantity"]
        },
        execute=flatten_position,
        risk_gated=True
    ))
    
    return reg


@pytest.fixture
def executor(registry, tmp_path):
    ks = AdvancedKillSwitch(tmp_path / "ks.json", tmp_path / "hb.json")
    rm = RiskManager()
    return SafetyActionExecutor(registry, ks, rm)


@pytest.fixture
def portfolio():
    return PortfolioSnapshot(cash=10000, equity=10000, total_exposure=0, positions=[])


@pytest.fixture
def session():
    return Session(id="s1", turn_count=0, has_summarized=False)


def test_unapproved_plan_is_not_executed(executor, session, portfolio):
    plan = SafetyActionPlan(
        plan_id="p1", mode="cancel_all", status="planned", reason="r",
        actions=[SafetyAction(type="cancel_order", description="d", params={"order_id": "1"})],
        requires_approval=True
    )
    
    result = executor.execute_plan(plan, session, portfolio, approved=False)
    assert result.status == "requires_approval"
    assert len(result.executed_actions) == 0


def test_approved_paper_plan_executes_successfully(executor, session, portfolio):
    plan = SafetyActionPlan(
        plan_id="p1", mode="cancel_all", status="planned", reason="r",
        actions=[SafetyAction(type="cancel_order", description="d", params={"order_id": "1"})],
        requires_approval=True
    )
    
    result = executor.execute_plan(plan, session, portfolio, mode="paper", approved=True)
    assert result.status == "completed"
    assert len(result.executed_actions) == 1
    assert result.executed_actions[0].action_type == "cancel_order"


def test_missing_tool_returns_failure(executor, session, portfolio):
    plan = SafetyActionPlan(
        plan_id="p1", mode="normal", status="planned", reason="r",
        actions=[SafetyAction(type="notify_user", description="d", params={})],
        requires_approval=False
    )
    
    result = executor.execute_plan(plan, session, portfolio, approved=True)
    assert result.status == "failed"
    assert "not found in registry" in result.errors[0]


def test_no_op_plan_is_skipped_cleanly(executor, session, portfolio):
    plan = SafetyActionPlan(
        plan_id="p1", mode="normal", status="planned", reason="r",
        actions=[SafetyAction(type="no_op", description="d")],
        requires_approval=False
    )
    
    result = executor.execute_plan(plan, session, portfolio, approved=True)
    assert result.status == "completed"
    assert len(result.executed_actions) == 0
    assert len(result.skipped_actions) == 1


def test_flatten_blocked_if_risk_increases(executor, session, portfolio):
    # Set up portfolio with a long position
    portfolio.positions.append(RiskPosition(
        symbol="AAPL", quantity=10, average_price=100, market_price=100, notional=1000, side="long"
    ))
    portfolio.equity = 10000
    portfolio.total_exposure = 1000

    # Create a plan to "flatten" by BUYING more (which increases risk)
    plan = SafetyActionPlan(
        plan_id="p1", mode="flatten_all", status="planned", reason="r",
        actions=[SafetyAction(type="flatten_position", description="d", params={"symbol": "AAPL", "side": "buy", "quantity": 10})],
        requires_approval=True
    )
    
    result = executor.execute_plan(plan, session, portfolio, approved=True)
    assert result.status == "failed"
    assert "Risk Manager blocked flattening" in result.errors[0]
