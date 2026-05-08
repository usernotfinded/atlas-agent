import pytest
from typing import Any, Union
from atlas_agent.tools.registry import ToolRegistry, CONTEXT_WINDOW_FULL_DESC_THRESHOLD
from atlas_agent.tools.spec import ToolSpec, ModelCapabilities, ToolCall, ToolError, ToolResult
from atlas_agent.core.types import Session

def sample_func(req_arg: str, opt_arg: int = 5) -> str:
    return f"{req_arg}_{opt_arg}"

def test_registry_registration_and_validation():
    registry = ToolRegistry()
    
    valid_spec = ToolSpec(
        name="test_tool",
        description_full="Full",
        description_compact="Compact",
        input_schema={
            "type": "object",
            "properties": {
                "req_arg": {"type": "string"},
                "opt_arg": {"type": "integer"}
            },
            "required": ["req_arg"]
        },
        execute=sample_func
    )
    
    # Should not raise
    registry.register(valid_spec)
    assert registry.get_tool("test_tool").name == "test_tool"

def test_registry_validation_missing_required_arg():
    registry = ToolRegistry()
    
    invalid_spec = ToolSpec(
        name="test_tool_invalid",
        description_full="Full",
        description_compact="Compact",
        input_schema={
            "type": "object",
            "properties": {
                "req_arg": {"type": "string"},
                "missing_in_func": {"type": "string"}
            },
            "required": ["req_arg", "missing_in_func"]
        },
        execute=sample_func
    )
    
    with pytest.raises(ValueError, match="missing from callable signature"):
        registry.register(invalid_spec)

def test_registry_validation_missing_schema_property():
    registry = ToolRegistry()
    
    invalid_spec = ToolSpec(
        name="test_tool_invalid_2",
        description_full="Full",
        description_compact="Compact",
        input_schema={
            "type": "object",
            "properties": {},
            "required": []
        },
        execute=sample_func
    )
    
    with pytest.raises(ValueError, match="not defined in input_schema"):
        registry.register(invalid_spec)

def test_describe_for_model():
    registry = ToolRegistry()
    spec = ToolSpec(
        name="desc_test",
        description_full="This is the full description",
        description_compact="Compact desc",
        input_schema={"type": "object"},
        execute=lambda: "ok"
    )
    registry.register(spec)
    
    # Test compact
    cap_compact = ModelCapabilities(context_window=CONTEXT_WINDOW_FULL_DESC_THRESHOLD - 1000, supports_native_tools=True)
    descs_compact = registry.describe_for_model(cap_compact)
    assert len(descs_compact) == 1
    assert descs_compact[0].description == "Compact desc"
    
    # Test full
    cap_full = ModelCapabilities(context_window=CONTEXT_WINDOW_FULL_DESC_THRESHOLD + 1000, supports_native_tools=True)
    descs_full = registry.describe_for_model(cap_full)
    assert descs_full[0].description == "This is the full description"

class EmptyGuardrailChain:
    def evaluate(self, tool_call: ToolCall, session: Session) -> Union[ToolResult, ToolError, None]:
        return None

class MockRejectGuardrailChain:
    def evaluate(self, tool_call: ToolCall, session: Session) -> Union[ToolResult, ToolError, None]:
        return ToolError(
            error_type="risk_rejected",
            message="Blocked by mock guardrail",
            is_retryable=False,
            suggested_action="Stop"
        )

def test_execute_empty_guardrail():
    registry = ToolRegistry()
    spec = ToolSpec(
        name="exec_test",
        description_full="Full",
        description_compact="Compact",
        input_schema={"type": "object", "properties": {"req_arg": {"type": "string"}}, "required": ["req_arg"]},
        execute=sample_func
    )
    registry.register(spec)
    
    call = ToolCall(id="1", name="exec_test", arguments={"req_arg": "hello"})
    session = Session(id="s1", turn_count=1, has_summarized=False)
    
    res = registry.execute(call, EmptyGuardrailChain(), session)
    assert isinstance(res, ToolResult)
    assert res.data == "hello_5"
    assert res.error is False

def test_execute_rejected_by_guardrail():
    registry = ToolRegistry()
    spec = ToolSpec(
        name="exec_test",
        description_full="Full",
        description_compact="Compact",
        input_schema={"type": "object"},
        execute=lambda: "ok"
    )
    registry.register(spec)
    
    call = ToolCall(id="1", name="exec_test", arguments={})
    session = Session(id="s1", turn_count=1, has_summarized=False)
    
    res = registry.execute(call, MockRejectGuardrailChain(), session)
    assert isinstance(res, ToolError)
    assert res.error_type == "risk_rejected"

def test_execute_disabled_tool():
    registry = ToolRegistry()
    spec = ToolSpec(
        name="disabled_tool",
        description_full="Full",
        description_compact="Compact",
        input_schema={"type": "object"},
        execute=lambda: "ok",
        default_enabled=False
    )
    registry.register(spec)
    
    call = ToolCall(id="1", name="disabled_tool", arguments={})
    session = Session(id="s1", turn_count=1, has_summarized=False)
    
    res = registry.execute(call, EmptyGuardrailChain(), session)
    assert isinstance(res, ToolError)
    assert res.error_type == "unavailable"
    
    # Override
    registry.enabled_tools_config["disabled_tool"] = True
    res2 = registry.execute(call, EmptyGuardrailChain(), session)
    assert isinstance(res2, ToolResult)
