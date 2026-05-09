from __future__ import annotations

import pytest
from pathlib import Path

from atlas_agent.agent.loop import AgentLoop, DefaultGuardrailChain
from atlas_agent.audit.writer import AuditWriter
from atlas_agent.core.types import Session
from atlas_agent.tools.registry import ToolRegistry
from atlas_agent.tools.spec import LLMResponse, ModelCapabilities

class MockProvider:
    def __init__(self, responses):
        self.responses = responses
    def complete(self, **kwargs):
        return self.responses.pop(0)
    def capabilities(self):
        return ModelCapabilities(context_window=128000, supports_native_tools=True)

def test_agent_loop_emits_audit_events(tmp_path: Path):
    audit_path = tmp_path / "audit.jsonl"
    writer = AuditWriter(audit_path)
    
    registry = ToolRegistry()
    guardrails = DefaultGuardrailChain(registry)
    
    provider = MockProvider([
        LLMResponse(text="Done", is_final=True)
    ])
    
    loop = AgentLoop(provider, registry, guardrails, audit_writer=writer)
    session = Session(id="s1", turn_count=0, has_summarized=False)
    
    loop.run("Objective", session, "System", run_id="run_1")
    
    lines = audit_path.read_text().splitlines()
    assert len(lines) >= 3 # run_started, provider_called, provider_response, run_completed
    
    events = [line for line in lines if "run_started" in line]
    assert len(events) == 1
    assert '"run_id":"run_1"' in events[0]
