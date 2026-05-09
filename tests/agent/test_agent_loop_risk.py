from __future__ import annotations

import pytest
from pathlib import Path

from atlas_agent.agent.loop import AgentLoop, DefaultGuardrailChain
from atlas_agent.audit.writer import AuditWriter
from atlas_agent.core.types import Session
from atlas_agent.risk.manager import RiskManager
from atlas_agent.risk.limits import RiskLimits
from atlas_agent.tools.registry import ToolRegistry
from atlas_agent.tools.spec import LLMResponse, ToolCall, ToolSpec, ModelCapabilities

class MockProvider:
    def __init__(self, responses):
        self.responses = responses
    def complete(self, **kwargs):
        return self.responses.pop(0)
    def capabilities(self):
        return ModelCapabilities(context_window=128000, supports_native_tools=True)

def test_agent_loop_blocks_risk_gated_tool(tmp_path: Path):
    audit_path = tmp_path / "audit.jsonl"
    writer = AuditWriter(audit_path)
    
    reg = ToolRegistry()
    def propose_order(symbol: str, quantity: float, price: float):
        return "filled"
    
    reg.register(ToolSpec(
        name="propose_order",
        description_full="propose",
        description_compact="propose",
        input_schema={
            "type": "object", 
            "properties": {
                "symbol": {"type": "string"},
                "quantity": {"type": "number"},
                "price": {"type": "number"}
            }, 
            "required": ["symbol", "quantity", "price"]
        },
        execute=propose_order,
        risk_gated=True
    ))
    
    # Set limit very low to force block
    limits = RiskLimits(max_single_trade_notional=1.0)
    risk_manager = RiskManager(limits=limits, audit_writer=writer)
    
    provider = MockProvider([
        LLMResponse(text="Trading", tool_calls=[
            ToolCall(id="c1", name="propose_order", arguments={"symbol": "AAPL", "quantity": 10, "price": 150.0})
        ], is_final=False)
    ])
    
    loop = AgentLoop(provider, reg, DefaultGuardrailChain(reg), risk_manager=risk_manager, audit_writer=writer)
    session = Session(id="s1", turn_count=0, has_summarized=False)
    
    result = loop.run("Trade", session, "System")
    
    assert result.status == "blocked"
    assert "Risk Manager blocked" in result.errors[0]
    
    # Verify audit event
    lines = audit_path.read_text().splitlines()
    assert any("risk_evaluation_blocked" in line for line in lines)
    assert any("tool_call_blocked" in line for line in lines)
