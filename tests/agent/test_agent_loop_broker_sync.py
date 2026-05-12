from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from atlas_agent.agent.loop import AgentLoop, DefaultGuardrailChain
from atlas_agent.audit.writer import AuditWriter
from atlas_agent.core.types import Session
from atlas_agent.risk.manager import RiskManager
from atlas_agent.risk.limits import RiskLimits
from atlas_agent.risk.models import PortfolioSnapshot, RiskPosition, PendingOrder
from atlas_agent.tools.registry import ToolRegistry
from atlas_agent.tools.spec import LLMResponse, ToolCall, ToolSpec, ModelCapabilities

class MockProvider:
    def __init__(self, responses):
        self.responses = responses
    def complete(self, **kwargs):
        return self.responses.pop(0)
    def capabilities(self):
        return ModelCapabilities(context_window=128000, supports_native_tools=True)

def test_agent_loop_receives_synced_portfolio_snapshot(tmp_path: Path):
    audit_path = tmp_path / "audit.jsonl"
    writer = AuditWriter(audit_path)
    
    # Setup a snapshot with a pending order
    portfolio = PortfolioSnapshot(
        cash=10000, equity=10000, total_exposure=0,
        open_orders=[PendingOrder(order_id="p1", symbol="AAPL", side="buy", quantity=10, limit_price=100, status="open")]
    )
    
    reg = ToolRegistry()
    def propose_order(symbol: str, side: str, quantity: float, order_type: str, limit_price: float): return "ok"
    reg.register(ToolSpec(
        name="propose_order", 
        description_full="d", 
        description_compact="c", 
        input_schema={
            "type": "object", 
            "properties": {
                "symbol": {"type": "string"},
                "side": {"type": "string"},
                "quantity": {"type": "number"},
                "order_type": {"type": "string"},
                "limit_price": {"type": "number"},
            },
            "required": ["symbol", "side", "quantity", "order_type", "limit_price"]
        },
        execute=propose_order,
        risk_gated=True
    ))
    
    # Limit: 1500. Pending AAPL: 1000. New AAPL buy: 600. Total 1600 > 1500.
    limits = RiskLimits(max_position_notional=1500.0)
    rm = RiskManager(limits=limits, audit_writer=writer)
    
    provider = MockProvider([
        LLMResponse(text="Trade", tool_calls=[
            ToolCall(
                id="c1",
                name="propose_order",
                arguments={
                    "symbol": "AAPL",
                    "side": "buy",
                    "quantity": 6,
                    "order_type": "limit",
                    "limit_price": 100.0,
                },
            )
        ], is_final=False)
    ])
    
    loop = AgentLoop(provider, reg, DefaultGuardrailChain(reg), risk_manager=rm, audit_writer=writer)
    session = Session(id="s1", turn_count=0, has_summarized=False)
    
    # Run loop passing the synced portfolio
    result = loop.run("Trade", session, "System", portfolio_snapshot=portfolio)
    
    assert result.status == "blocked"
    assert "Risk Manager blocked" in result.errors[0]
    assert "Risk violations detected" in result.errors[0]
    
    # Verify audit shows pending orders were considered
    lines = audit_path.read_text().splitlines()
    assert any('"pending_quantity_delta":10.0' in line for line in lines)
