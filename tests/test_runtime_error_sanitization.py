# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_runtime_error_sanitization.py
# PURPOSE: Verifies runtime error sanitization behavior and regression
#         expectations.
# DEPS:    json, pathlib, unittest, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.agent.loop import AgentLoop, DefaultGuardrailChain
from atlas_agent.agent.result import AgentResult
from atlas_agent.brokers.paper import PaperBroker
from atlas_agent.execution.order import FlattenResult
from atlas_agent.portfolio.state import PortfolioState
from atlas_agent.runtime_errors import make_safe_runtime_error, SafeRuntimeError
from atlas_agent.safety.kill_switch import KillSwitchController
from atlas_agent.tools.registry import ToolRegistry


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_make_safe_runtime_error_never_leaks_raw_text() -> None:
    exc = RuntimeError("api_key=raw-secret-token token=raw-secret-token")
    safe = make_safe_runtime_error(operation="provider_complete", exc=exc)
    assert "raw-secret-token" not in safe.message
    assert "api_key" not in safe.message
    assert safe.code == "operation_failed"
    assert safe.operation == "provider_complete"


def test_make_safe_runtime_error_classifies_transport() -> None:
    safe = make_safe_runtime_error(operation="provider_complete", exc=TimeoutError("conn timeout"))
    assert safe.code == "transport_error"
    assert safe.message == "transport request failed"


def test_make_safe_runtime_error_classifies_validation() -> None:
    safe = make_safe_runtime_error(operation="provider_complete", exc=ValueError("bad input"))
    assert safe.code == "validation_error"
    assert safe.message == "input validation failed"


def test_agent_loop_provider_exception_is_sanitized() -> None:
    class ExplodingProvider:
        def complete(self, **kwargs):
            raise RuntimeError("api_key=raw-secret-token token=raw-secret-token")

        def capabilities(self):
            return {}

    loop = AgentLoop(
        provider=ExplodingProvider(),  # type: ignore
        tool_registry=ToolRegistry(),
        guardrails=DefaultGuardrailChain(ToolRegistry()),
    )
    from atlas_agent.core.types import Session

    result = loop.run(
        user_objective="test",
        session=Session(id="test", turn_count=0, has_summarized=False),
        system_prompt="test",
    )
    assert result.status == "error"
    assert result.errors
    assert "raw-secret-token" not in result.errors[0]
    assert "api_key" not in result.errors[0]


def test_agent_loop_provider_exception_audit_payload_is_sanitized(tmp_path: Path) -> None:
    class ExplodingProvider:
        def complete(self, **kwargs):
            raise RuntimeError("api_key=raw-secret-token token=raw-secret-token")

        def capabilities(self):
            return {}

    from atlas_agent.audit import AuditWriter

    audit_writer = AuditWriter(tmp_path / "audit.jsonl")
    loop = AgentLoop(
        provider=ExplodingProvider(),  # type: ignore
        tool_registry=ToolRegistry(),
        guardrails=DefaultGuardrailChain(ToolRegistry()),
        audit_writer=audit_writer,
    )
    from atlas_agent.core.types import Session

    loop.run(
        user_objective="test",
        session=Session(id="test", turn_count=0, has_summarized=False),
        system_prompt="test",
        run_id="run-test",
    )

    audit_lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    failed_event = json.loads(audit_lines[-1])
    assert failed_event["event_type"] == "run_failed"
    payload = failed_event["payload"]
    serialized = json.dumps(payload, sort_keys=True)
    assert "raw-secret-token" not in serialized
    assert "api_key" not in serialized
    assert payload["code"] == "operation_failed"
    assert payload["operation"] == "provider_complete"


def test_kill_switch_flatten_exception_is_sanitized(tmp_path: Path) -> None:
    class ExplodingBroker:
        def flatten_all(self, strategy: str = "market", bps: int = 25) -> FlattenResult:
            raise RuntimeError("api_key=raw-secret-token token=raw-secret-token")

    controller = KillSwitchController(
        state_path=tmp_path / "state.json",
        enabled_flag_path=tmp_path / "enabled.flag",
        lock_path=tmp_path / "lock",
    )

    # We need to bypass the file-based state for this test
    with patch.object(controller, "_read_state") as mock_read:
        from atlas_agent.safety.kill_switch import KillSwitchState
        mock_read.return_value = KillSwitchState.disabled()
        result = controller._run_flatten(
            broker=ExplodingBroker(),  # type: ignore
            strategy="market",
            bps=25,
        )

    assert result.status == "failed"
    assert "raw-secret-token" not in result.message
    assert "api_key" not in result.message
    assert result.message == "broker operation failed"


def test_kill_switch_flatten_exception_audit_safe(tmp_path: Path) -> None:
    class ExplodingBroker:
        def flatten_all(self, strategy: str = "market", bps: int = 25) -> FlattenResult:
            raise RuntimeError("api_key=raw-secret-token token=raw-secret-token")

    events: list[dict] = []

    def audit_hook(event_type: str, actor: str, payload: dict[str, object]) -> None:
        events.append({"event_type": event_type, "actor": actor, "payload": payload})

    from atlas_agent.safety.kill_switch import KillSwitchState

    controller = KillSwitchController(
        state_path=tmp_path / "state.json",
        enabled_flag_path=tmp_path / "enabled.flag",
        lock_path=tmp_path / "lock",
        audit_hook=audit_hook,
    )

    with patch.object(controller, "_read_state", return_value=KillSwitchState.disabled()):
        controller.enable(
            mode="flatten",
            actor="user:1",
            broker=ExplodingBroker(),  # type: ignore
        )

    serialized = json.dumps(events, sort_keys=True)
    assert "raw-secret-token" not in serialized
    assert "api_key" not in serialized
