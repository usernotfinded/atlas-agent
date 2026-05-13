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
    def propose_order(symbol: str, side: str, quantity: float, order_type: str, limit_price: float):
        return "filled"
    
    reg.register(ToolSpec(
        name="propose_order",
        description_full="propose",
        description_compact="propose",
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
    
    # Set limit very low to force block
    limits = RiskLimits(max_single_trade_notional=1.0)
    risk_manager = RiskManager(limits=limits, audit_writer=writer)
    
    provider = MockProvider([
        LLMResponse(text="Trading", tool_calls=[
            ToolCall(
                id="c1",
                name="propose_order",
                arguments={
                    "symbol": "AAPL",
                    "side": "buy",
                    "quantity": 10,
                    "order_type": "limit",
                    "limit_price": 150.0,
                },
            )
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


def test_agent_loop_rejects_market_order_without_reference_price(tmp_path: Path):
    audit_path = tmp_path / "audit.jsonl"
    writer = AuditWriter(audit_path)

    reg = ToolRegistry()

    def propose_order(symbol: str, side: str, quantity: float, order_type: str):
        return "filled"

    reg.register(ToolSpec(
        name="propose_order",
        description_full="propose",
        description_compact="propose",
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "side": {"type": "string"},
                "quantity": {"type": "number"},
                "order_type": {"type": "string"},
            },
            "required": ["symbol", "side", "quantity", "order_type"],
        },
        execute=propose_order,
        risk_gated=True,
    ))

    limits = RiskLimits(max_single_trade_notional=10_000.0)
    risk_manager = RiskManager(limits=limits, audit_writer=writer)
    provider = MockProvider([
        LLMResponse(text="Trading", tool_calls=[
            ToolCall(
                id="c1",
                name="propose_order",
                arguments={"symbol": "AAPL", "side": "buy", "quantity": 10, "order_type": "market"},
            )
        ], is_final=False)
    ])

    loop = AgentLoop(provider, reg, DefaultGuardrailChain(reg), risk_manager=risk_manager, audit_writer=writer)
    session = Session(id="s1", turn_count=0, has_summarized=False)

    result = loop.run("Trade", session, "System")

    assert result.status == "blocked"
    assert "reference/current/estimated execution price" in result.errors[0]
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert any("tool_call_blocked" in line for line in lines)


def test_agent_loop_allows_limit_order_with_valid_limit_price(tmp_path: Path):
    audit_path = tmp_path / "audit.jsonl"
    writer = AuditWriter(audit_path)

    reg = ToolRegistry()

    def propose_order(symbol: str, side: str, quantity: float, order_type: str, limit_price: float):
        return "filled"

    reg.register(ToolSpec(
        name="propose_order",
        description_full="propose",
        description_compact="propose",
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "side": {"type": "string"},
                "quantity": {"type": "number"},
                "order_type": {"type": "string"},
                "limit_price": {"type": "number"},
            },
            "required": ["symbol", "side", "quantity", "order_type", "limit_price"],
        },
        execute=propose_order,
        risk_gated=True,
        approval_gated=True,
    ))

    limits = RiskLimits(max_single_trade_notional=10_000.0)
    risk_manager = RiskManager(limits=limits, audit_writer=writer)
    provider = MockProvider([
        LLMResponse(text="Trading", tool_calls=[
            ToolCall(
                id="c1",
                name="propose_order",
                arguments={
                    "symbol": "AAPL",
                    "side": "buy",
                    "quantity": 10,
                    "order_type": "limit",
                    "limit_price": 15.0,
                },
            )
        ], is_final=False)
    ])

    loop = AgentLoop(provider, reg, DefaultGuardrailChain(reg), risk_manager=risk_manager, audit_writer=writer)
    session = Session(id="s1", turn_count=0, has_summarized=False)

    result = loop.run("Trade", session, "System")

    assert result.status == "approval_required"


def test_agent_loop_rejects_malformed_numeric_risk_fields(tmp_path: Path):
    audit_path = tmp_path / "audit.jsonl"
    writer = AuditWriter(audit_path)

    reg = ToolRegistry()

    def propose_order(symbol: str, side: str, quantity: float, order_type: str, limit_price: float):
        return "filled"

    reg.register(ToolSpec(
        name="propose_order",
        description_full="propose",
        description_compact="propose",
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "side": {"type": "string"},
                "quantity": {},
                "order_type": {"type": "string"},
                "limit_price": {"type": "number"},
            },
            "required": ["symbol", "side", "quantity", "order_type", "limit_price"],
        },
        execute=propose_order,
        risk_gated=True,
    ))

    limits = RiskLimits(max_single_trade_notional=10_000.0)
    risk_manager = RiskManager(limits=limits, audit_writer=writer)
    provider = MockProvider([
        LLMResponse(text="Trading", tool_calls=[
            ToolCall(
                id="c1",
                name="propose_order",
                arguments={
                    "symbol": "AAPL",
                    "side": "buy",
                    "quantity": "not-a-number",
                    "order_type": "limit",
                    "limit_price": 15.0,
                },
            )
        ], is_final=False)
    ])

    loop = AgentLoop(provider, reg, DefaultGuardrailChain(reg), risk_manager=risk_manager, audit_writer=writer)
    session = Session(id="s1", turn_count=0, has_summarized=False)

    result = loop.run("Trade", session, "System")

    assert result.status == "blocked"
    assert "invalid numeric field: quantity" in result.errors[0]


@pytest.mark.parametrize(
    ("bad_quantity", "expected_fragment"),
    [
        ("nan", "quantity must be a positive finite number"),
        ("inf", "quantity must be a positive finite number"),
        ("-inf", "quantity must be a positive finite number"),
        (0, "quantity must be positive"),
        (-1, "quantity must be positive"),
    ],
)
def test_agent_loop_rejects_non_finite_or_non_positive_quantity(
    tmp_path: Path,
    bad_quantity,
    expected_fragment: str,
):
    audit_path = tmp_path / "audit.jsonl"
    writer = AuditWriter(audit_path)

    reg = ToolRegistry()

    def propose_order(symbol: str, side: str, quantity: float, order_type: str, limit_price: float):
        return "filled"

    reg.register(ToolSpec(
        name="propose_order",
        description_full="propose",
        description_compact="propose",
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "side": {"type": "string"},
                "quantity": {},
                "order_type": {"type": "string"},
                "limit_price": {"type": "number"},
            },
            "required": ["symbol", "side", "quantity", "order_type", "limit_price"],
        },
        execute=propose_order,
        risk_gated=True,
    ))

    limits = RiskLimits(max_single_trade_notional=10_000.0)
    risk_manager = RiskManager(limits=limits, audit_writer=writer)
    provider = MockProvider([
        LLMResponse(text="Trading", tool_calls=[
            ToolCall(
                id="c1",
                name="propose_order",
                arguments={
                    "symbol": "AAPL",
                    "side": "buy",
                    "quantity": bad_quantity,
                    "order_type": "limit",
                    "limit_price": 15.0,
                },
            )
        ], is_final=False)
    ])

    loop = AgentLoop(provider, reg, DefaultGuardrailChain(reg), risk_manager=risk_manager, audit_writer=writer)
    session = Session(id="s1", turn_count=0, has_summarized=False)
    result = loop.run("Trade", session, "System")

    assert result.status == "blocked"
    assert expected_fragment in result.errors[0]
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert any("tool_call_blocked" in line for line in lines)


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("price", "nan"),
        ("price", "inf"),
        ("price", "-inf"),
        ("reference_price", "nan"),
        ("reference_price", "inf"),
        ("reference_price", "-inf"),
        ("price", 0),
        ("price", -1),
    ],
)
def test_agent_loop_rejects_non_finite_or_non_positive_market_reference_price(
    tmp_path: Path,
    field_name: str,
    bad_value,
):
    audit_path = tmp_path / "audit.jsonl"
    writer = AuditWriter(audit_path)

    reg = ToolRegistry()

    def propose_order(symbol: str, side: str, quantity: float, order_type: str, **kwargs):
        return "filled"

    reg.register(ToolSpec(
        name="propose_order",
        description_full="propose",
        description_compact="propose",
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "side": {"type": "string"},
                "quantity": {"type": "number"},
                "order_type": {"type": "string"},
                "price": {},
                "reference_price": {},
                "current_price": {},
                "estimated_price": {},
            },
            "required": ["symbol", "side", "quantity", "order_type"],
        },
        execute=propose_order,
        risk_gated=True,
    ))

    limits = RiskLimits(max_single_trade_notional=10_000.0)
    risk_manager = RiskManager(limits=limits, audit_writer=writer)
    args = {
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 5,
        "order_type": "market",
    }
    args[field_name] = bad_value
    provider = MockProvider([
        LLMResponse(text="Trading", tool_calls=[ToolCall(id="c1", name="propose_order", arguments=args)], is_final=False)
    ])

    loop = AgentLoop(provider, reg, DefaultGuardrailChain(reg), risk_manager=risk_manager, audit_writer=writer)
    session = Session(id="s1", turn_count=0, has_summarized=False)
    result = loop.run("Trade", session, "System")

    assert result.status == "blocked"
    assert "must be" in result.errors[0]
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert any("tool_call_blocked" in line for line in lines)


def test_agent_loop_allows_market_order_with_valid_positive_finite_price(tmp_path: Path):
    audit_path = tmp_path / "audit.jsonl"
    writer = AuditWriter(audit_path)

    reg = ToolRegistry()

    def propose_order(symbol: str, side: str, quantity: float, order_type: str, price: float):
        return "filled"

    reg.register(ToolSpec(
        name="propose_order",
        description_full="propose",
        description_compact="propose",
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "side": {"type": "string"},
                "quantity": {"type": "number"},
                "order_type": {"type": "string"},
                "price": {"type": "number"},
            },
            "required": ["symbol", "side", "quantity", "order_type", "price"],
        },
        execute=propose_order,
        risk_gated=True,
        approval_gated=True,
    ))

    limits = RiskLimits(max_single_trade_notional=10_000.0)
    risk_manager = RiskManager(limits=limits, audit_writer=writer)
    provider = MockProvider([
        LLMResponse(text="Trading", tool_calls=[
            ToolCall(
                id="c1",
                name="propose_order",
                arguments={
                    "symbol": "AAPL",
                    "side": "buy",
                    "quantity": 2,
                    "order_type": "market",
                    "price": 100.0,
                },
            )
        ], is_final=False)
    ])

    loop = AgentLoop(provider, reg, DefaultGuardrailChain(reg), risk_manager=risk_manager, audit_writer=writer)
    session = Session(id="s1", turn_count=0, has_summarized=False)
    result = loop.run("Trade", session, "System")

    assert result.status == "approval_required"


@pytest.mark.parametrize("bad_quantity", [True, False])
def test_agent_loop_rejects_boolean_quantity(tmp_path: Path, bad_quantity):
    audit_path = tmp_path / "audit.jsonl"
    writer = AuditWriter(audit_path)

    reg = ToolRegistry()

    def propose_order(symbol: str, side: str, quantity: float, order_type: str, limit_price: float):
        return "filled"

    reg.register(ToolSpec(
        name="propose_order",
        description_full="propose",
        description_compact="propose",
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "side": {"type": "string"},
                "quantity": {},
                "order_type": {"type": "string"},
                "limit_price": {"type": "number"},
            },
            "required": ["symbol", "side", "quantity", "order_type", "limit_price"],
        },
        execute=propose_order,
        risk_gated=True,
    ))

    limits = RiskLimits(max_single_trade_notional=10_000.0)
    risk_manager = RiskManager(limits=limits, audit_writer=writer)
    provider = MockProvider([
        LLMResponse(text="Trading", tool_calls=[
            ToolCall(
                id="c1",
                name="propose_order",
                arguments={
                    "symbol": "AAPL",
                    "side": "buy",
                    "quantity": bad_quantity,
                    "order_type": "limit",
                    "limit_price": 15.0,
                },
            )
        ], is_final=False)
    ])

    loop = AgentLoop(provider, reg, DefaultGuardrailChain(reg), risk_manager=risk_manager, audit_writer=writer)
    session = Session(id="s1", turn_count=0, has_summarized=False)
    result = loop.run("Trade", session, "System")

    assert result.status == "blocked"
    assert "invalid numeric field: quantity" in result.errors[0]
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert any("tool_call_blocked" in line for line in lines)


@pytest.mark.parametrize("bad_limit_price", [True, False])
def test_agent_loop_rejects_boolean_limit_price(tmp_path: Path, bad_limit_price):
    audit_path = tmp_path / "audit.jsonl"
    writer = AuditWriter(audit_path)

    reg = ToolRegistry()

    def propose_order(symbol: str, side: str, quantity: float, order_type: str, limit_price: float):
        return "filled"

    reg.register(ToolSpec(
        name="propose_order",
        description_full="propose",
        description_compact="propose",
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "side": {"type": "string"},
                "quantity": {"type": "number"},
                "order_type": {"type": "string"},
                "limit_price": {},
            },
            "required": ["symbol", "side", "quantity", "order_type", "limit_price"],
        },
        execute=propose_order,
        risk_gated=True,
    ))

    limits = RiskLimits(max_single_trade_notional=10_000.0)
    risk_manager = RiskManager(limits=limits, audit_writer=writer)
    provider = MockProvider([
        LLMResponse(text="Trading", tool_calls=[
            ToolCall(
                id="c1",
                name="propose_order",
                arguments={
                    "symbol": "AAPL",
                    "side": "buy",
                    "quantity": 5,
                    "order_type": "limit",
                    "limit_price": bad_limit_price,
                },
            )
        ], is_final=False)
    ])

    loop = AgentLoop(provider, reg, DefaultGuardrailChain(reg), risk_manager=risk_manager, audit_writer=writer)
    session = Session(id="s1", turn_count=0, has_summarized=False)
    result = loop.run("Trade", session, "System")

    assert result.status == "blocked"
    assert "invalid numeric field: limit_price" in result.errors[0]
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert any("tool_call_blocked" in line for line in lines)


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("price", True),
        ("price", False),
        ("reference_price", True),
        ("reference_price", False),
        ("current_price", True),
        ("current_price", False),
        ("estimated_price", True),
        ("estimated_price", False),
    ],
)
def test_agent_loop_rejects_boolean_market_reference_price(
    tmp_path: Path,
    field_name: str,
    bad_value,
):
    audit_path = tmp_path / "audit.jsonl"
    writer = AuditWriter(audit_path)

    reg = ToolRegistry()

    def propose_order(symbol: str, side: str, quantity: float, order_type: str, **kwargs):
        return "filled"

    reg.register(ToolSpec(
        name="propose_order",
        description_full="propose",
        description_compact="propose",
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "side": {"type": "string"},
                "quantity": {"type": "number"},
                "order_type": {"type": "string"},
                "price": {},
                "reference_price": {},
                "current_price": {},
                "estimated_price": {},
            },
            "required": ["symbol", "side", "quantity", "order_type"],
        },
        execute=propose_order,
        risk_gated=True,
    ))

    limits = RiskLimits(max_single_trade_notional=10_000.0)
    risk_manager = RiskManager(limits=limits, audit_writer=writer)
    args = {
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 5,
        "order_type": "market",
    }
    args[field_name] = bad_value
    provider = MockProvider([
        LLMResponse(text="Trading", tool_calls=[ToolCall(id="c1", name="propose_order", arguments=args)], is_final=False)
    ])

    loop = AgentLoop(provider, reg, DefaultGuardrailChain(reg), risk_manager=risk_manager, audit_writer=writer)
    session = Session(id="s1", turn_count=0, has_summarized=False)
    result = loop.run("Trade", session, "System")

    assert result.status == "blocked"
    assert "invalid numeric field" in result.errors[0]
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert any("tool_call_blocked" in line for line in lines)
