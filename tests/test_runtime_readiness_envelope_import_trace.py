# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_runtime_readiness_envelope_import_trace.py
# PURPOSE: Verifies runtime readiness envelope import trace behavior and
#         regression expectations.
# DEPS:    json, subprocess, sys, pathlib.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent

_FORBIDDEN_MODULES = (
    "atlas_agent.cli",
    "atlas_agent.brokers",
    "atlas_agent.providers",
    "atlas_agent.execution",
    "atlas_agent.risk",
    "atlas_agent.safety",
    "atlas_agent.config",
    "requests",
    "httpx",
    "aiohttp",
    "websockets",
    "socket",
    "openai",
    "anthropic",
)


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _run_subprocess_code(code: str) -> tuple[int, str, str]:
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    return result.returncode, result.stdout, result.stderr


def _make_fixture_script(tmp_dir: str) -> str:
    return f"""
import json, hashlib
from pathlib import Path
tmp = Path({tmp_dir!r})

def fp(value):
    return "sha256:" + hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()

quality_gate = {{
    "artifact_type": "trading_quality_gate",
    "schema_version": "trading-quality-gate.v1",
    "mode": "paper",
    "run_id": "run-123",
    "symbol": "AAPL",
    "quality_state": "eligible_for_shadow_live_quality_review",
    "blockers": [],
}}
shadow_comparison = {{
    "artifact_type": "shadow_live_comparison",
    "schema_version": "shadow-live-comparison.v1",
    "run_id": "run-123",
    "symbol": "AAPL",
    "quality_state": "eligible_for_shadow_live_quality_review",
    "status": "matched",
    "freshness_assessment": {{"snapshot_age_seconds": 0}},
    "blockers": [],
}}
submit_conformance = {{
    "artifact_type": "gated_submit_conformance",
    "schema_version": "gated-submit-conformance.v1",
    "candidate": "CAND-006",
    "mode": "simulated_only",
    "run_id": "run-123",
    "symbol": "AAPL",
    "status": "dry_run_recorded",
    "as_of": "2026-06-24T10:00:00Z",
    "safety_assertions": {{
        "no_live_submit": True,
        "no_broker_called": True,
        "no_provider_called": True,
        "no_credentials_loaded": True,
    }},
    "dry_run_request": {{
        "transmission": {{
            "allowed": False,
            "broker_adapter": None,
            "provider": None,
        }}
    }},
    "blockers": [],
}}
runtime_envelope = {{
    "artifact_type": "runtime_readiness_envelope_fixture",
    "schema_version": "runtime-readiness-envelope-fixture.v1",
    "fixture_mode": "simulated/static",
    "run_id": "run-123",
    "symbol": "AAPL",
    "allowed_modes": ["paper", "shadow_live_readonly", "simulated"],
    "forbidden_modes": ["live", "live_submit"],
    "live_submit_enabled": False,
    "require_human_approval": True,
    "require_kill_switch_inactive": True,
    "require_risk_gate": True,
    "require_audit_recording": True,
    "require_broker_capability_manifest": True,
    "max_order_notional": "1000.00",
    "max_symbol_exposure": "5000.00",
    "max_daily_orders": 10,
    "max_daily_notional": "10000.00",
    "supported_order_types": ["market", "limit"],
    "supported_time_in_force": ["day"],
    "expires_at": "2026-06-24T12:00:00Z",
}}
broker_capabilities = {{
    "artifact_type": "broker_capability_manifest_fixture",
    "schema_version": "broker-capability-manifest-fixture.v1",
    "broker_label": "local-test-broker",
    "capabilities": {{"paper_trading": True}},
    "disabled_capabilities": [],
    "unsupported_order_types": [],
    "sandbox_only": True,
    "live_api_contact_allowed": False,
    "credentials_present": False,
    "endpoint_present": False,
    "captured_at": "2026-06-24T09:00:00Z",
    "expires_at": "2026-06-24T12:00:00Z",
}}
operator_policy = {{
    "artifact_type": "operator_policy_fixture",
    "schema_version": "operator-policy-fixture.v1",
    "requires_manual_review": True,
    "requires_explicit_approval": True,
    "approval_scope": "simulated_only",
    "unattended_operation_allowed": False,
    "max_runtime_window_seconds": 3600,
    "max_actions_per_session": 10,
    "allowed_symbols": ["AAPL"],
    "blocked_symbols": [],
    "expires_at": "2026-06-24T12:00:00Z",
}}
kill_switch_policy = {{
    "artifact_type": "kill_switch_policy_fixture",
    "schema_version": "kill-switch-policy-fixture.v1",
    "kill_switch_required": True,
    "default_state_on_missing_runtime": "blocked",
    "default_state_on_unknown_runtime": "blocked",
    "operator_override_allowed": False,
    "expires_at": "2026-06-24T12:00:00Z",
}}
audit_policy = {{
    "artifact_type": "audit_policy_fixture",
    "schema_version": "audit-policy-fixture.v1",
    "audit_required": True,
    "append_only_required": True,
    "hash_chain_required": True,
    "local_artifact_recording_required": True,
    "live_audit_chain_claimed": False,
    "expires_at": "2026-06-24T12:00:00Z",
}}
(tmp / "quality_gate.json").write_text(json.dumps(quality_gate), encoding="utf-8")
(tmp / "shadow_comparison.json").write_text(json.dumps(shadow_comparison), encoding="utf-8")
(tmp / "submit_conformance.json").write_text(json.dumps(submit_conformance), encoding="utf-8")
(tmp / "runtime_envelope.json").write_text(json.dumps(runtime_envelope), encoding="utf-8")
(tmp / "broker_capabilities.json").write_text(json.dumps(broker_capabilities), encoding="utf-8")
(tmp / "operator_policy.json").write_text(json.dumps(operator_policy), encoding="utf-8")
(tmp / "kill_switch_policy.json").write_text(json.dumps(kill_switch_policy), encoding="utf-8")
(tmp / "audit_policy.json").write_text(json.dumps(audit_policy), encoding="utf-8")

# CAND-006 fixtures for the isolated-route regression check.
order_intent = {{
    "artifact_type": "gated_submit_order_intent",
    "schema_version": "gated-submit-order-intent.v1",
    "intent_kind": "hypothetical",
    "intent_id": "intent-001",
    "run_id": "run-123",
    "symbol": "AAPL",
    "side": "buy",
    "quantity": "1",
    "order_type": "limit",
    "limit_price": "100",
    "time_in_force": "day",
    "created_at": "2026-06-24T09:00:00Z",
}}
order_fp = fp(order_intent)
cand006_kill_switch = {{
    "artifact_type": "gated_submit_kill_switch_fixture",
    "schema_version": "gated-submit-kill-switch.v1",
    "fixture_mode": "simulated",
    "scope": "conformance_rehearsal_only",
    "state": "inactive",
    "captured_at": "2026-06-24T09:00:00Z",
    "expires_at": "2026-06-24T11:00:00Z",
}}
cand006_risk_envelope = {{
    "artifact_type": "gated_submit_risk_envelope_fixture",
    "schema_version": "gated-submit-risk-envelope.v1",
    "fixture_mode": "simulated",
    "represents": "RiskManager_evaluation",
    "evaluation_mode": "paper",
    "intent_fingerprint": order_fp,
    "captured_at": "2026-06-24T09:00:00Z",
    "expires_at": "2026-06-24T11:00:00Z",
    "decision": "allowed",
    "evaluated_price": "100",
    "evaluated_notional": "100",
    "checks": [{{"rule": "max_position_size", "passed": True}}],
    "violations": [],
    "limits_digest": "sha256:" + "a" * 64,
    "portfolio_snapshot_digest": "sha256:" + "b" * 64,
}}
risk_fp = fp(cand006_risk_envelope)
cand006_approval = {{
    "artifact_type": "gated_submit_approval_fixture",
    "schema_version": "gated-submit-approval-fixture.v1",
    "fixture_mode": "simulated",
    "scope": "conformance_rehearsal_only",
    "fixture_id": "approval-001",
    "intent_fingerprint": order_fp,
    "risk_envelope_fingerprint": risk_fp,
    "decision": "approved",
    "actor_label": "simulated-reviewer",
    "approved_at": "2026-06-24T09:00:00Z",
    "expires_at": "2026-06-24T11:00:00Z",
}}
(tmp / "order_intent.json").write_text(json.dumps(order_intent), encoding="utf-8")
(tmp / "cand006_kill_switch.json").write_text(json.dumps(cand006_kill_switch), encoding="utf-8")
(tmp / "cand006_risk_envelope.json").write_text(json.dumps(cand006_risk_envelope), encoding="utf-8")
(tmp / "cand006_approval.json").write_text(json.dumps(cand006_approval), encoding="utf-8")
"""


def _make_cand006_fixture_script(tmp_dir: str) -> str:
    return f"""
import json, hashlib
from pathlib import Path
tmp = Path({tmp_dir!r})

def fp(value):
    return "sha256:" + hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()

quality_gate = {{
    "artifact_type": "trading_quality_gate",
    "schema_version": "trading-quality-gate.v1",
    "mode": "paper",
    "run_id": "run-123",
    "symbol": "AAPL",
    "quality_state": "eligible_for_shadow_live_quality_review",
    "blockers": [],
}}
shadow_comparison = {{
    "artifact_type": "shadow_live_comparison",
    "schema_version": "shadow-live-comparison.v1",
    "run_id": "run-123",
    "symbol": "AAPL",
    "quality_state": "eligible_for_shadow_live_quality_review",
    "status": "matched",
    "freshness_assessment": {{"snapshot_age_seconds": 0}},
    "blockers": [],
}}
order_intent = {{
    "artifact_type": "gated_submit_order_intent",
    "schema_version": "gated-submit-order-intent.v1",
    "intent_kind": "hypothetical",
    "intent_id": "intent-001",
    "run_id": "run-123",
    "symbol": "AAPL",
    "side": "buy",
    "quantity": "1",
    "order_type": "limit",
    "limit_price": "100",
    "time_in_force": "day",
    "created_at": "2026-06-24T09:00:00Z",
}}
order_fp = fp(order_intent)
kill_switch = {{
    "artifact_type": "gated_submit_kill_switch_fixture",
    "schema_version": "gated-submit-kill-switch.v1",
    "fixture_mode": "simulated",
    "scope": "conformance_rehearsal_only",
    "state": "inactive",
    "captured_at": "2026-06-24T09:00:00Z",
    "expires_at": "2026-06-24T11:00:00Z",
}}
risk_envelope = {{
    "artifact_type": "gated_submit_risk_envelope_fixture",
    "schema_version": "gated-submit-risk-envelope.v1",
    "fixture_mode": "simulated",
    "represents": "RiskManager_evaluation",
    "evaluation_mode": "paper",
    "intent_fingerprint": order_fp,
    "captured_at": "2026-06-24T09:00:00Z",
    "expires_at": "2026-06-24T11:00:00Z",
    "decision": "allowed",
    "evaluated_price": "100",
    "evaluated_notional": "100",
    "checks": [{{"rule": "max_position_size", "passed": True}}],
    "violations": [],
    "limits_digest": "sha256:" + "a" * 64,
    "portfolio_snapshot_digest": "sha256:" + "b" * 64,
}}
risk_fp = fp(risk_envelope)
approval = {{
    "artifact_type": "gated_submit_approval_fixture",
    "schema_version": "gated-submit-approval-fixture.v1",
    "fixture_mode": "simulated",
    "scope": "conformance_rehearsal_only",
    "fixture_id": "approval-001",
    "intent_fingerprint": order_fp,
    "risk_envelope_fingerprint": risk_fp,
    "decision": "approved",
    "actor_label": "simulated-reviewer",
    "approved_at": "2026-06-24T09:00:00Z",
    "expires_at": "2026-06-24T11:00:00Z",
}}
(tmp / "quality_gate.json").write_text(json.dumps(quality_gate), encoding="utf-8")
(tmp / "shadow_comparison.json").write_text(json.dumps(shadow_comparison), encoding="utf-8")
(tmp / "order_intent.json").write_text(json.dumps(order_intent), encoding="utf-8")
(tmp / "kill_switch.json").write_text(json.dumps(kill_switch), encoding="utf-8")
(tmp / "risk_envelope.json").write_text(json.dumps(risk_envelope), encoding="utf-8")
(tmp / "approval.json").write_text(json.dumps(approval), encoding="utf-8")
"""


def test_configless_positive_route_imports_no_forbidden_modules(tmp_path: Path) -> None:
    tmp_dir = str(tmp_path)
    script = f"""
{_make_fixture_script(tmp_dir)}
import io, sys, json
from atlas_agent.cli_bootstrap import main
old_stdout = sys.stdout
old_stderr = sys.stderr
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
try:
    rc = main([
        "agent", "readiness-envelope",
        "--quality-gate", str(tmp / "quality_gate.json"),
        "--shadow-comparison", str(tmp / "shadow_comparison.json"),
        "--submit-conformance", str(tmp / "submit_conformance.json"),
        "--runtime-envelope", str(tmp / "runtime_envelope.json"),
        "--broker-capabilities", str(tmp / "broker_capabilities.json"),
        "--operator-policy", str(tmp / "operator_policy.json"),
        "--kill-switch-policy", str(tmp / "kill_switch_policy.json"),
        "--audit-policy", str(tmp / "audit_policy.json"),
        "--output-dir", str(tmp / "out"),
        "--as-of", "2026-06-24T10:00:00Z",
    ])
finally:
    sys.stdout = old_stdout
    sys.stderr = old_stderr
print(rc)
print(json.dumps(sorted(sys.modules)))
"""
    rc, stdout, stderr = _run_subprocess_code(script)
    output = stdout + stderr
    lines = output.strip().splitlines()
    assert lines[0] == "0", output
    loaded = json.loads(lines[-1])
    for forbidden in _FORBIDDEN_MODULES:
        assert forbidden not in loaded, f"forbidden module imported: {forbidden}"


def test_configless_positive_route_returns_zero(tmp_path: Path) -> None:
    tmp_dir = str(tmp_path)
    script = f"""
{_make_fixture_script(tmp_dir)}
import io, sys
from atlas_agent.cli_bootstrap import main
old_stdout = sys.stdout
old_stderr = sys.stderr
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
try:
    rc = main([
        "agent", "readiness-envelope",
        "--quality-gate", str(tmp / "quality_gate.json"),
        "--shadow-comparison", str(tmp / "shadow_comparison.json"),
        "--submit-conformance", str(tmp / "submit_conformance.json"),
        "--runtime-envelope", str(tmp / "runtime_envelope.json"),
        "--broker-capabilities", str(tmp / "broker_capabilities.json"),
        "--operator-policy", str(tmp / "operator_policy.json"),
        "--kill-switch-policy", str(tmp / "kill_switch_policy.json"),
        "--audit-policy", str(tmp / "audit_policy.json"),
        "--output-dir", str(tmp / "out"),
        "--as-of", "2026-06-24T10:00:00Z",
    ])
finally:
    sys.stdout = old_stdout
    sys.stderr = old_stderr
print(rc)
"""
    rc, stdout, stderr = _run_subprocess_code(script)
    output = stdout + stderr
    lines = output.strip().splitlines()
    assert lines[-1] == "0", output


def test_forbidden_modules_not_imported_on_any_configless_route(tmp_path: Path) -> None:
    """Hard boundary: configless readiness-envelope must not load runtime trading modules."""
    tmp_dir = str(tmp_path)
    script = f"""
{_make_fixture_script(tmp_dir)}
import io, sys, json
from atlas_agent.cli_bootstrap import main
old_stdout = sys.stdout
old_stderr = sys.stderr
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
try:
    main([
        "agent", "readiness-envelope",
        "--quality-gate", str(tmp / "quality_gate.json"),
        "--shadow-comparison", str(tmp / "shadow_comparison.json"),
        "--submit-conformance", str(tmp / "submit_conformance.json"),
        "--runtime-envelope", str(tmp / "runtime_envelope.json"),
        "--broker-capabilities", str(tmp / "broker_capabilities.json"),
        "--operator-policy", str(tmp / "operator_policy.json"),
        "--kill-switch-policy", str(tmp / "kill_switch_policy.json"),
        "--audit-policy", str(tmp / "audit_policy.json"),
        "--output-dir", str(tmp / "out"),
        "--as-of", "2026-06-24T10:00:00Z",
    ])
finally:
    sys.stdout = old_stdout
    sys.stderr = old_stderr
print(json.dumps(sorted(sys.modules)))
"""
    rc, stdout, stderr = _run_subprocess_code(script)
    output = stdout + stderr
    lines = output.strip().splitlines()
    loaded = json.loads(lines[-1])
    for forbidden in _FORBIDDEN_MODULES:
        assert forbidden not in loaded, f"forbidden module imported: {forbidden}"


def test_legacy_cli_delegation_with_workspace() -> None:
    script = """
import io, sys
from atlas_agent.cli_bootstrap import main
old_stdout = sys.stdout
old_stderr = sys.stderr
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
try:
    main(["--workspace", "/tmp/nonexistent-ws-cand007", "agent", "readiness-envelope", "--help"])
except SystemExit:
    pass
finally:
    sys.stdout = old_stdout
    sys.stderr = old_stderr
import sys
print("atlas_agent.cli" in sys.modules)
"""
    rc, stdout, stderr = _run_subprocess_code(script)
    output = stdout + stderr
    lines = output.strip().splitlines()
    assert lines[-1] == "True", output


def test_delegated_readiness_envelope_extra_imports_legacy_cli() -> None:
    script = """
import io, sys
from atlas_agent.cli_bootstrap import main
old_stdout = sys.stdout
old_stderr = sys.stderr
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
try:
    main(["agent", "readiness-envelope-extra", "--help"])
except SystemExit:
    pass
finally:
    sys.stdout = old_stdout
    sys.stderr = old_stderr
import sys
print("atlas_agent.cli" in sys.modules)
"""
    rc, stdout, stderr = _run_subprocess_code(script)
    output = stdout + stderr
    lines = output.strip().splitlines()
    assert lines[-1] == "True", output


def test_cand006_configless_route_still_isolated(tmp_path: Path) -> None:
    tmp_dir = str(tmp_path)
    script = f"""
{_make_cand006_fixture_script(tmp_dir)}
import io, sys, json
from atlas_agent.cli_bootstrap import main
old_stdout = sys.stdout
old_stderr = sys.stderr
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
try:
    rc = main([
        "agent", "submit-conformance",
        "--quality-gate", str(tmp / "quality_gate.json"),
        "--shadow-comparison", str(tmp / "shadow_comparison.json"),
        "--order-intent", str(tmp / "order_intent.json"),
        "--kill-switch", str(tmp / "kill_switch.json"),
        "--risk-envelope", str(tmp / "risk_envelope.json"),
        "--approval", str(tmp / "approval.json"),
        "--output-dir", str(tmp / "out-cand006"),
        "--as-of", "2026-06-24T10:00:00Z",
    ])
finally:
    sys.stdout = old_stdout
    sys.stderr = old_stderr
print(rc)
print("atlas_agent.cli" in sys.modules)
print(json.dumps(sorted(sys.modules)))
"""
    rc, stdout, stderr = _run_subprocess_code(script)
    output = stdout + stderr
    lines = output.strip().splitlines()
    assert lines[0] == "0", output
    assert lines[1] == "False", output
    loaded = json.loads(lines[-1])
    for forbidden in _FORBIDDEN_MODULES:
        assert forbidden not in loaded, f"forbidden module imported: {forbidden}"
