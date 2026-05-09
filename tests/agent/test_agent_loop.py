from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from atlas_agent.agent.loop import AgentLoop, DefaultGuardrailChain
from atlas_agent.core.types import Session, UserApprovalPending
from atlas_agent.providers.base import AIProvider, ProviderRequest
from atlas_agent.tools.registry import ToolRegistry
from atlas_agent.tools.spec import (
    LLMResponse, 
    ToolCall, 
    ToolSpec, 
    ToolResult, 
    ToolError,
    ModelCapabilities,
)

class MockProvider(AIProvider):
    def __init__(self, responses: list[LLMResponse]):
        self.responses = responses
        self.calls = []

    def complete(self, system_prompt, messages, tools, model=None, temperature=0.0):
        self.calls.append((system_prompt, messages, tools))
        if not self.responses:
            return LLMResponse(text="Done.", is_final=True)
        return self.responses.pop(0)

    def summarize(self, text, max_tokens):
        return text[:max_tokens]

    def capabilities(self):
        return ModelCapabilities(context_window=128000, supports_native_tools=True)

    def generate(self, request):
        return None

@pytest.fixture
def registry():
    reg = ToolRegistry()
    def test_tool(arg: str):
        return f"result_{arg}"
    
    reg.register(ToolSpec(
        name="test_tool",
        description_full="test",
        description_compact="test",
        input_schema={"type": "object", "properties": {"arg": {"type": "string"}}, "required": ["arg"]},
        execute=test_tool
    ))

    def gated_tool():
        return "gated"

    reg.register(ToolSpec(
        name="gated_tool",
        description_full="gated",
        description_compact="gated",
        input_schema={"type": "object"},
        execute=gated_tool,
        approval_gated=True
    ))

    return reg

@pytest.fixture
def session():
    return Session(id="s1", turn_count=0, has_summarized=False)

def test_loop_stops_on_final_message(registry, session):
    provider = MockProvider([
        LLMResponse(text="Final answer", is_final=True)
    ])
    loop = AgentLoop(provider, registry, DefaultGuardrailChain(registry))
    
    result = loop.run("Task", session, "System")
    
    assert result.status == "complete"
    assert result.final_message == "Final answer"
    assert len(result.iterations) == 1

def test_loop_executes_one_valid_tool_call(registry, session):
    provider = MockProvider([
        LLMResponse(text="Thinking", tool_calls=[ToolCall(id="c1", name="test_tool", arguments={"arg": "val"})], is_final=False),
        LLMResponse(text="Got it", is_final=True)
    ])
    loop = AgentLoop(provider, registry, DefaultGuardrailChain(registry))
    
    result = loop.run("Task", session, "System")
    
    assert result.status == "complete"
    assert len(result.iterations) == 2
    assert result.total_tool_calls == 1
    assert result.iterations[0].tool_results[0].data == "result_val"

def test_loop_rejects_invalid_tool_arguments(registry, session):
    provider = MockProvider([
        LLMResponse(text="Thinking", tool_calls=[ToolCall(id="c1", name="test_tool", arguments={"wrong": "val"})], is_final=False)
    ])
    loop = AgentLoop(provider, registry, DefaultGuardrailChain(registry))
    
    result = loop.run("Task", session, "System")
    
    # ToolRegistry.execute handles validation errors
    assert len(result.iterations) == 2
    assert isinstance(result.iterations[0].tool_results[0], ToolError)
    assert result.iterations[0].tool_results[0].error_type == "validation"

def test_loop_stops_at_max_iterations(registry, session):
    provider = MockProvider([
        LLMResponse(text="Thinking", tool_calls=[ToolCall(id="c1", name="test_tool", arguments={"arg": "val"})], is_final=False)
        for _ in range(5)
    ])
    loop = AgentLoop(provider, registry, DefaultGuardrailChain(registry), max_iterations=3)
    
    result = loop.run("Task", session, "System")
    
    assert result.status == "max_iterations"
    assert len(result.iterations) == 3

def test_loop_stops_at_max_tool_calls(registry, session):
    provider = MockProvider([
        LLMResponse(text="Thinking", tool_calls=[
            ToolCall(id=f"c{i}", name="test_tool", arguments={"arg": str(i)}) for i in range(5)
        ], is_final=False)
    ])
    loop = AgentLoop(provider, registry, DefaultGuardrailChain(registry), max_tool_calls=3)
    
    result = loop.run("Task", session, "System")
    
    assert result.status == "max_tool_calls"
    assert result.total_tool_calls == 3

def test_approval_gated_tool_stops_loop(registry, session):
    provider = MockProvider([
        LLMResponse(text="Thinking", tool_calls=[ToolCall(id="c1", name="gated_tool", arguments={})], is_final=False)
    ])
    loop = AgentLoop(provider, registry, DefaultGuardrailChain(registry))
    
    result = loop.run("Task", session, "System")
    
    assert result.status == "approval_required"
    assert "approval" in result.diagnostics
