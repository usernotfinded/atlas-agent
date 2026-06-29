from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent

_FORBIDDEN_MODULES = (
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
import json, os
from pathlib import Path
tmp = Path({tmp_dir!r})
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
    "freshness_assessment": {{}},
    "blockers": [],
}}
import hashlib
def fp(value):
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()
order_fp = fp(order_intent)
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
kill_switch = {{
    "artifact_type": "gated_submit_kill_switch_fixture",
    "schema_version": "gated-submit-kill-switch.v1",
    "fixture_mode": "simulated",
    "scope": "conformance_rehearsal_only",
    "state": "inactive",
    "captured_at": "2026-06-24T09:00:00Z",
    "expires_at": "2026-06-24T11:00:00Z",
}}
(tmp / "order_intent.json").write_text(json.dumps(order_intent), encoding="utf-8")
(tmp / "quality_gate.json").write_text(json.dumps(quality_gate), encoding="utf-8")
(tmp / "shadow_comparison.json").write_text(json.dumps(shadow_comparison), encoding="utf-8")
(tmp / "risk_envelope.json").write_text(json.dumps(risk_envelope), encoding="utf-8")
(tmp / "approval.json").write_text(json.dumps(approval), encoding="utf-8")
(tmp / "kill_switch.json").write_text(json.dumps(kill_switch), encoding="utf-8")
"""


def test_configless_positive_route_imports_no_forbidden_modules(tmp_path: Path) -> None:
    tmp_dir = str(tmp_path)
    script = f"""
{_make_fixture_script(tmp_dir)}
import io, sys
from atlas_agent.cli_bootstrap import main
old_stdout = sys.stdout
sys.stdout = io.StringIO()
try:
    rc = main([
        "agent", "submit-conformance",
        "--quality-gate", str(tmp / "quality_gate.json"),
        "--shadow-comparison", str(tmp / "shadow_comparison.json"),
        "--order-intent", str(tmp / "order_intent.json"),
        "--kill-switch", str(tmp / "kill_switch.json"),
        "--risk-envelope", str(tmp / "risk_envelope.json"),
        "--approval", str(tmp / "approval.json"),
        "--output-dir", str(tmp / "out"),
        "--as-of", "2026-06-24T10:00:00Z",
    ])
finally:
    sys.stdout = old_stdout
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


def test_delegated_help_imports_legacy_cli() -> None:
    script = """
import io, sys
from atlas_agent.cli_bootstrap import main
old_stdout = sys.stdout
sys.stdout = io.StringIO()
try:
    rc = main(["--help"])
finally:
    sys.stdout = old_stdout
import sys
print(rc)
print("atlas_agent.cli" in sys.modules)
"""
    rc, stdout, stderr = _run_subprocess_code(script)
    output = stdout + stderr
    lines = output.strip().splitlines()
    assert lines[0] == "0", output
    assert lines[-1] == "True", output


def test_delegated_validate_imports_legacy_cli() -> None:
    script = """
from atlas_agent.cli_bootstrap import main
rc = main(["validate"])
import sys
print("atlas_agent.cli" in sys.modules)
"""
    rc, stdout, stderr = _run_subprocess_code(script)
    output = stdout + stderr
    lines = output.strip().splitlines()
    assert lines[-1] == "True", output


def test_delegated_workspace_variant_imports_legacy_cli() -> None:
    script = """
import io, sys
from atlas_agent.cli_bootstrap import main
old_stdout = sys.stdout
old_stderr = sys.stderr
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
try:
    main(["--workspace", "/tmp/nonexistent-ws-cand006", "agent", "submit-conformance", "--help"])
except SystemExit:
    pass
finally:
    sys.stdout = old_stdout
    sys.stderr = old_stderr
print("atlas_agent.cli" in sys.modules)
"""
    rc, stdout, stderr = _run_subprocess_code(script)
    output = stdout + stderr
    lines = output.strip().splitlines()
    assert lines[-1] == "True", output


def test_delegated_unknown_subcommand_imports_legacy_cli() -> None:
    script = """
import io, sys
from atlas_agent.cli_bootstrap import main
old_stdout = sys.stdout
old_stderr = sys.stderr
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
try:
    main(["agent", "submit-conformance-extra", "--help"])
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
