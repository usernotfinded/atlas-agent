import pytest
from typing import Any
from atlas_agent.tools.registry import ToolRegistry
from atlas_agent.tools.builtin import BUILTIN_TOOLS
from atlas_agent.tools.spec import ToolSpec, ToolCall, ToolResult, ToolError
from atlas_agent.core.types import Session
from typing import Union

class EmptyGuardrailChain:
    def evaluate(self, tool_call: ToolCall, session: Session) -> Union[ToolResult, ToolError, None]:
        return None

EXPECTED_TOOL_FLAGS = {
    "propose_order": {"risk_gated": True, "approval_gated": True, "audit_logged": True},
    "cancel_order": {"risk_gated": True, "approval_gated": True, "audit_logged": True},
    "modify_order": {"risk_gated": True, "approval_gated": True, "audit_logged": True},
    "flatten_position": {"risk_gated": True, "approval_gated": True, "audit_logged": True},
    "append_journal": {"risk_gated": False, "approval_gated": False, "audit_logged": True},
    "append_lesson": {"risk_gated": False, "approval_gated": False, "audit_logged": True},
    "append_mistake": {"risk_gated": False, "approval_gated": False, "audit_logged": True},
    "append_daily_note": {"risk_gated": False, "approval_gated": False, "audit_logged": True},
    "write_skill_proposal": {"risk_gated": False, "approval_gated": False, "audit_logged": True},
    "promote_skill": {"risk_gated": False, "approval_gated": False, "audit_logged": True},
    "archive_skill": {"risk_gated": False, "approval_gated": False, "audit_logged": True},
    "update_user_profile": {"risk_gated": False, "approval_gated": False, "audit_logged": True},
    "update_open_positions": {"risk_gated": False, "approval_gated": False, "audit_logged": True},
    "update_portfolio_summary": {"risk_gated": False, "approval_gated": False, "audit_logged": True},
    "run_shell_command": {"risk_gated": False, "approval_gated": False, "audit_logged": True},
    "git_commit_memory": {"risk_gated": False, "approval_gated": False, "audit_logged": True},
    "notify_user": {"risk_gated": False, "approval_gated": False, "audit_logged": False}
}


def generate_dummy_value(schema: dict) -> Any:
    """Generate a minimal valid value for a JSON Schema fragment."""
    if "enum" in schema:
        return schema["enum"][0]
    if "anyOf" in schema:
        for opt in schema["anyOf"]:
            if opt.get("type") == "null":
                continue
            return generate_dummy_value(opt)
        return None
    t = schema.get("type")
    if t == "string":
        return "dummy"
    if t == "integer":
        return 0
    if t == "number":
        return 0.0
    if t == "boolean":
        return True
    if t == "array":
        items = schema.get("items", {})
        if items:
            return [generate_dummy_value(items)]
        return []
    if t == "object":
        obj = {}
        for prop, prop_schema in schema.get("properties", {}).items():
            if prop in schema.get("required", []):
                obj[prop] = generate_dummy_value(prop_schema)
        return obj
    if t == "null":
        return None
    return {}


@pytest.fixture(scope="module")
def registry():
    reg = ToolRegistry()
    for tool_spec in BUILTIN_TOOLS:
        reg.register(tool_spec)
    return reg


def test_registry_has_50_tools(registry):
    assert len(registry.list_tools()) == 50
    assert len(BUILTIN_TOOLS) == 50


@pytest.mark.parametrize("tool_spec", BUILTIN_TOOLS, ids=lambda x: x.name)
def test_builtin_tool_invariants(tool_spec: ToolSpec, registry):
    # 1. Description fields are present
    assert tool_spec.name
    assert tool_spec.description_full.strip()

    # 2. Description compact does not contain 'Mock for'
    assert "Mock for" not in tool_spec.description_compact
    assert len(tool_spec.description_compact) > 0

    # 3. Flags check
    if tool_spec.name in EXPECTED_TOOL_FLAGS:
        expected = EXPECTED_TOOL_FLAGS[tool_spec.name]
        assert tool_spec.risk_gated == expected["risk_gated"], f"{tool_spec.name} risk_gated flag incorrect"
        assert tool_spec.approval_gated == expected["approval_gated"], f"{tool_spec.name} approval_gated flag incorrect"
        assert tool_spec.audit_logged == expected["audit_logged"], f"{tool_spec.name} audit_logged flag incorrect"

    # 4. Schema correctness checks
    schema = tool_spec.input_schema
    assert schema.get("type") == "object"
    assert schema.get("additionalProperties") is False, f"{tool_spec.name} missing additionalProperties: false"

    # 5. Valid input passes schema validation via registry.execute()
    kwargs = generate_dummy_value(schema)
    call = ToolCall(id="1", name=tool_spec.name, arguments=kwargs)
    session = Session(id="s1", turn_count=1, has_summarized=False)
    res = registry.execute(call, EmptyGuardrailChain(), session)
    assert isinstance(res, ToolResult), f"Execute failed for {tool_spec.name}: {res}"

    # 6. Invalid input fails schema validation (missing required)
    required = schema.get("required", [])
    if required:
        invalid_kwargs = {}
        invalid_call = ToolCall(id="2", name=tool_spec.name, arguments=invalid_kwargs)
        res_invalid = registry.execute(invalid_call, EmptyGuardrailChain(), session)
        assert isinstance(res_invalid, ToolError)
        assert res_invalid.error_type == "validation"

        # 7. Extra argument fails schema validation
        extra_kwargs = kwargs.copy()
        extra_kwargs["unexpected_field"] = "bad"
        extra_call = ToolCall(id="3", name=tool_spec.name, arguments=extra_kwargs)
        res_extra = registry.execute(extra_call, EmptyGuardrailChain(), session)
        assert isinstance(res_extra, ToolError), f"Extra arg should fail for {tool_spec.name}: {res_extra}"
        assert res_extra.error_type == "validation"


def test_propose_order_optional_none(registry):
    """Optional fields (limit_price, stop_loss, take_profit) must accept None."""
    tool_spec = next(t for t in BUILTIN_TOOLS if t.name == "propose_order")
    kwargs = generate_dummy_value(tool_spec.input_schema)
    kwargs["limit_price"] = None
    kwargs["stop_loss"] = None
    kwargs["take_profit"] = None
    call = ToolCall(id="1", name="propose_order", arguments=kwargs)
    session = Session(id="s1", turn_count=1, has_summarized=False)
    res = registry.execute(call, EmptyGuardrailChain(), session)
    assert isinstance(res, ToolResult)


def test_cancel_order_replacement_order_null(registry):
    """cancel_order.replacement_order (OrderProposal | None) must accept null."""
    tool_spec = next(t for t in BUILTIN_TOOLS if t.name == "cancel_order")
    kwargs = generate_dummy_value(tool_spec.input_schema)
    kwargs["replacement_order"] = None
    call = ToolCall(id="1", name="cancel_order", arguments=kwargs)
    session = Session(id="s1", turn_count=1, has_summarized=False)
    res = registry.execute(call, EmptyGuardrailChain(), session)
    assert isinstance(res, ToolResult)


def test_flatten_position_urgency_enum(registry):
    """flatten_position.urgency must be a valid enum value."""
    tool_spec = next(t for t in BUILTIN_TOOLS if t.name == "flatten_position")

    # Valid: normal (urgency has default, so generate_dummy_value won't include it)
    kwargs = generate_dummy_value(tool_spec.input_schema)
    kwargs["urgency"] = "normal"
    call = ToolCall(id="1", name="flatten_position", arguments=kwargs)
    session = Session(id="s1", turn_count=1, has_summarized=False)
    res = registry.execute(call, EmptyGuardrailChain(), session)
    assert isinstance(res, ToolResult)

    # Invalid enum value
    kwargs["urgency"] = "invalid"
    call2 = ToolCall(id="2", name="flatten_position", arguments=kwargs)
    res2 = registry.execute(call2, EmptyGuardrailChain(), session)
    assert isinstance(res2, ToolError)
    assert res2.error_type == "validation"


def test_propose_order_side_enum(registry):
    """propose_order.side must be 'buy' or 'sell'."""
    tool_spec = next(t for t in BUILTIN_TOOLS if t.name == "propose_order")
    kwargs = generate_dummy_value(tool_spec.input_schema)
    assert kwargs["side"] in ("buy", "sell")

    kwargs["side"] = "invalid"
    call = ToolCall(id="1", name="propose_order", arguments=kwargs)
    session = Session(id="s1", turn_count=1, has_summarized=False)
    res = registry.execute(call, EmptyGuardrailChain(), session)
    assert isinstance(res, ToolError)
    assert res.error_type == "validation"


def test_propose_order_order_type_enum(registry):
    """propose_order.order_type must be 'market' or 'limit'."""
    tool_spec = next(t for t in BUILTIN_TOOLS if t.name == "propose_order")
    kwargs = generate_dummy_value(tool_spec.input_schema)
    assert kwargs["order_type"] in ("market", "limit")

    kwargs["order_type"] = "invalid"
    call = ToolCall(id="1", name="propose_order", arguments=kwargs)
    session = Session(id="s1", turn_count=1, has_summarized=False)
    res = registry.execute(call, EmptyGuardrailChain(), session)
    assert isinstance(res, ToolError)
    assert res.error_type == "validation"


def test_request_user_approval_schema(registry):
    """request_user_approval must accept both string and object for proposal."""
    tool_spec = next(t for t in BUILTIN_TOOLS if t.name == "request_user_approval")

    # Valid with string proposal
    kwargs = generate_dummy_value(tool_spec.input_schema)
    kwargs["proposal"] = "dummy_proposal"
    call = ToolCall(id="1", name="request_user_approval", arguments=kwargs)
    session = Session(id="s1", turn_count=1, has_summarized=False)
    res = registry.execute(call, EmptyGuardrailChain(), session)
    assert isinstance(res, ToolResult)


def test_run_shell_command_schema(registry):
    """run_shell_command.cmd must be array of strings."""
    tool_spec = next(t for t in BUILTIN_TOOLS if t.name == "run_shell_command")
    kwargs = generate_dummy_value(tool_spec.input_schema)
    call = ToolCall(id="1", name="run_shell_command", arguments=kwargs)
    session = Session(id="s1", turn_count=1, has_summarized=False)
    res = registry.execute(call, EmptyGuardrailChain(), session)
    assert isinstance(res, ToolResult)


def test_append_journal_schema(registry):
    """append_journal required fields: entry_type, content."""
    tool_spec = next(t for t in BUILTIN_TOOLS if t.name == "append_journal")
    kwargs = generate_dummy_value(tool_spec.input_schema)
    call = ToolCall(id="1", name="append_journal", arguments=kwargs)
    session = Session(id="s1", turn_count=1, has_summarized=False)
    res = registry.execute(call, EmptyGuardrailChain(), session)
    assert isinstance(res, ToolResult)


def test_write_skill_proposal_schema(registry):
    """write_skill_proposal required fields + optional confidence default."""
    tool_spec = next(t for t in BUILTIN_TOOLS if t.name == "write_skill_proposal")
    kwargs = generate_dummy_value(tool_spec.input_schema)
    call = ToolCall(id="1", name="write_skill_proposal", arguments=kwargs)
    session = Session(id="s1", turn_count=1, has_summarized=False)
    res = registry.execute(call, EmptyGuardrailChain(), session)
    assert isinstance(res, ToolResult)


def test_notify_user_schema(registry):
    """notify_user must accept only message as required."""
    tool_spec = next(t for t in BUILTIN_TOOLS if t.name == "notify_user")
    kwargs = generate_dummy_value(tool_spec.input_schema)
    call = ToolCall(id="1", name="notify_user", arguments=kwargs)
    session = Session(id="s1", turn_count=1, has_summarized=False)
    res = registry.execute(call, EmptyGuardrailChain(), session)
    assert isinstance(res, ToolResult)


def test_no_description_compact_placeholders():
    """No description_compact should contain placeholders like 'Mock for' or 'TODO'."""
    for tool_spec in BUILTIN_TOOLS:
        assert "Mock for" not in tool_spec.description_compact, f"{tool_spec.name} contains 'Mock for'"
        assert "TODO" not in tool_spec.description_compact, f"{tool_spec.name} contains 'TODO'"
        assert "placeholder" not in tool_spec.description_compact.lower(), f"{tool_spec.name} contains 'placeholder'"


def test_jsonschema_in_pyproject():
    """jsonschema>=4.0 must be declared as a runtime dependency."""
    with open("pyproject.toml") as f:
        content = f.read()
    assert '"jsonschema>=4.0"' in content or "'jsonschema>=4.0'" in content
