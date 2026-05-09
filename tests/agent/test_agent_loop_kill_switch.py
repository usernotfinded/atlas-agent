from __future__ import annotations

import pytest
from pathlib import Path

from atlas_agent.agent.loop import AgentLoop, DefaultGuardrailChain
from atlas_agent.audit.writer import AuditWriter
from atlas_agent.core.types import Session
from atlas_agent.safety.kill_switch import AdvancedKillSwitch
from atlas_agent.tools.registry import ToolRegistry
from atlas_agent.tools.spec import LLMResponse, ToolCall, ToolSpec, ModelCapabilities

class MockProvider:
    def __init__(self, responses):
        self.responses = responses
    def complete(self, **kwargs):
        return self.responses.pop(0)
    def capabilities(self):
        return ModelCapabilities(context_window=128000, supports_native_tools=True)

def test_agent_loop_blocks_on_kill_switch(tmp_path: Path):
    audit_path = tmp_path / "audit.jsonl"
    writer = AuditWriter(audit_path)
    
    state_path = tmp_path / "ks.json"
    hb_path = tmp_path / "hb.json"
    ks = AdvancedKillSwitch(state_path, hb_path, audit_writer=writer)
    ks.set_mode("soft_pause", reason="emergency")
    
    reg = ToolRegistry()
    def some_tool(): return "ok"
    reg.register(ToolSpec(
        name="some_tool", 
        description_full="d", 
        description_compact="c", 
        input_schema={"type": "object"}, 
        execute=some_tool,
        risk_gated=True
    ))
    
    provider = MockProvider([
        LLMResponse(text="Trading", tool_calls=[ToolCall(id="c1", name="some_tool", arguments={})], is_final=False)
    ])
    
    loop = AgentLoop(provider, reg, DefaultGuardrailChain(reg), kill_switch=ks, audit_writer=writer)
    session = Session(id="s1", turn_count=0, has_summarized=False)
    
    result = loop.run("Task", session, "System")
    
    assert result.status == "blocked"
    assert "Kill switch" in result.errors[0]
    
    # Verify audit event
    lines = audit_path.read_text().splitlines()
    assert any("kill_switch_blocked" in line for line in lines)


def test_agent_loop_surfaces_safety_action_plan(tmp_path: Path):
    audit_path = tmp_path / "audit.jsonl"
    writer = AuditWriter(audit_path)
    
    state_path = tmp_path / "ks.json"
    hb_path = tmp_path / "hb.json"
    ks = AdvancedKillSwitch(state_path, hb_path, audit_writer=writer)
    ks.set_mode("cancel_all", reason="emergency")
    
    reg = ToolRegistry()
    def some_tool(): return "ok"
    reg.register(ToolSpec(
        name="some_tool", 
        description_full="d", 
        description_compact="c", 
        input_schema={"type": "object"}, 
        execute=some_tool,
        risk_gated=True
    ))
    
    provider = MockProvider([
        LLMResponse(text="Trading", tool_calls=[ToolCall(id="c1", name="some_tool", arguments={})], is_final=False)
    ])
    
    loop = AgentLoop(provider, reg, DefaultGuardrailChain(reg), kill_switch=ks, audit_writer=writer)
    session = Session(id="s1", turn_count=0, has_summarized=False)
    
    # Simulate having an open order
    result = loop.run("Task", session, "System", open_order_ids=["ord_1"])
    
    assert result.status == "blocked"
    assert "safety_action_plan" in result.diagnostics
    plan = result.diagnostics["safety_action_plan"]
    assert plan["mode"] == "cancel_all"
    assert len(plan["actions"]) == 1
    assert plan["actions"][0]["type"] == "cancel_order"
    
    # Verify audit event
    lines = audit_path.read_text().splitlines()
    assert any("safety_action_requires_approval" in line for line in lines)
