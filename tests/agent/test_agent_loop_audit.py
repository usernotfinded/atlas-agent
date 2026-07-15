# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/agent/test_agent_loop_audit.py
# PURPOSE: Verifies agent loop audit behavior and regression expectations.
# DEPS:    json, pytest, pathlib, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
import pytest
from pathlib import Path

from atlas_agent.agent.loop import AgentLoop, DefaultGuardrailChain
from atlas_agent.audit.writer import AuditWriter
from atlas_agent.core.types import Session
from atlas_agent.tools.registry import ToolRegistry
from atlas_agent.tools.spec import LLMResponse, ModelCapabilities

# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

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
    
    # Check log
    lines = audit_path.read_text().splitlines()
    assert len(lines) >= 3
    
    # Check manifest
    manifest_path = tmp_path / "manifests" / "run_1.json"
    assert manifest_path.exists()
    manifest_data = json.loads(manifest_path.read_text())
    assert manifest_data["run_id"] == "run_1"
    assert manifest_data["status"] == "completed"
    assert manifest_data["event_count"] >= 3
    assert manifest_data["root_hash"] is not None

def test_agent_loop_audit_hides_raw_prompts_by_default(tmp_path: Path):
    audit_path = tmp_path / "audit.jsonl"
    writer = AuditWriter(audit_path)
    
    registry = ToolRegistry()
    guardrails = DefaultGuardrailChain(registry)
    
    provider = MockProvider([
        LLMResponse(text="Provider says hi", is_final=True)
    ])
    
    # Defaults: log_raw_prompts=False, log_provider_text=False
    loop = AgentLoop(provider, registry, guardrails, audit_writer=writer)
    session = Session(id="s1", turn_count=0, has_summarized=False)
    
    loop.run("Super secret objective", session, "System", run_id="run_1")
    
    lines = audit_path.read_text().splitlines()
    events = [json.loads(line) for line in lines]
    
    run_started = next(e for e in events if e["event_type"] == "run_started")
    assert "user_objective" not in run_started["payload"]
    assert "prompt_hash" in run_started["payload"]
    
    provider_response = next(e for e in events if e["event_type"] == "provider_response")
    assert "text" not in provider_response["payload"]
    assert "response_hash" in provider_response["payload"]
    assert "length" in provider_response["payload"]

def test_agent_loop_audit_logs_raw_if_enabled(tmp_path: Path):
    audit_path = tmp_path / "audit.jsonl"
    writer = AuditWriter(audit_path)
    
    registry = ToolRegistry()
    guardrails = DefaultGuardrailChain(registry)
    
    provider = MockProvider([
        LLMResponse(text="Provider says hi", is_final=True)
    ])
    
    loop = AgentLoop(provider, registry, guardrails, audit_writer=writer, log_raw_prompts=True, log_provider_text=True)
    session = Session(id="s1", turn_count=0, has_summarized=False)
    
    loop.run("Super secret objective", session, "System", run_id="run_1")
    
    lines = audit_path.read_text().splitlines()
    events = [json.loads(line) for line in lines]
    
    run_started = next(e for e in events if e["event_type"] == "run_started")
    assert run_started["payload"]["user_objective"] == "Super secret objective"
    
    provider_response = next(e for e in events if e["event_type"] == "provider_response")
    assert provider_response["payload"]["text"] == "Provider says hi"
