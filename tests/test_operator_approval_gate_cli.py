from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from atlas_agent.agent.operator_approval_gate_cli import (
    CLI_DESCRIPTION,
    _UNSAFE_FLAGS,
    main,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _ack_digest() -> str:
    from atlas_agent.agent.operator_approval_gate import _compute_acknowledgment_digest

    return _compute_acknowledgment_digest()


def _make_fixture_set(tmp_path: Path) -> dict[str, Path]:
    quality_gate = {
        "artifact_type": "trading_quality_gate",
        "schema_version": "trading-quality-gate.v1",
        "mode": "paper",
        "run_id": "run-123",
        "symbol": "AAPL",
        "quality_state": "eligible_for_shadow_live_quality_review",
        "blockers": [],
    }
    shadow_comparison = {
        "artifact_type": "shadow_live_comparison",
        "schema_version": "shadow-live-comparison.v1",
        "run_id": "run-123",
        "symbol": "AAPL",
        "quality_state": "eligible_for_shadow_live_quality_review",
        "status": "matched",
        "freshness_assessment": {"snapshot_age_seconds": 0},
        "blockers": [],
    }
    submit_conformance = {
        "artifact_type": "gated_submit_conformance",
        "schema_version": "gated-submit-conformance.v1",
        "candidate": "CAND-006",
        "mode": "simulated_only",
        "run_id": "run-123",
        "symbol": "AAPL",
        "status": "dry_run_recorded",
        "as_of": "2026-06-24T09:00:00Z",
        "safety_assertions": {
            "simulated_only": True,
            "no_live_submit": True,
            "no_broker_called": True,
            "no_provider_called": True,
            "no_credentials_loaded": True,
            "no_runtime_state_mutation": True,
            "no_order_instantiated": True,
            "transmission_blocked": True,
            "json_authoritative": True,
        },
        "dry_run_request": {
            "transmission": {
                "allowed": False,
                "broker_adapter": None,
                "provider": None,
            }
        },
        "blockers": [],
    }
    readiness_envelope = {
        "artifact_type": "runtime_readiness_envelope",
        "schema_version": "runtime-readiness-envelope.v1",
        "candidate": "CAND-007",
        "mode": "simulated_only",
        "status": "readiness_envelope_recorded",
        "exit_code": 0,
        "as_of": "2026-06-24T10:00:00Z",
        "run_id": "run-123",
        "symbol": "AAPL",
        "blockers": [],
        "envelope_assertions": {
            "live_submit_forbidden": True,
            "human_approval_required": True,
            "kill_switch_required": True,
            "risk_gate_required": True,
            "audit_recording_required": True,
            "broker_manifest_required": True,
            "operator_policy_fail_closed": True,
            "all_upstream_statuses_accepted": True,
            "no_credentials_in_fixtures": True,
            "no_endpoints_in_fixtures": True,
            "no_account_ids_in_fixtures": True,
            "cand006_transmission_blocked": True,
        },
    }
    operator_identity = {
        "artifact_type": "operator_identity_fixture",
        "schema_version": "operator-identity-fixture.v1",
        "operator_id": "operator-local-001",
        "operator_role": "local_evidence_reviewer",
        "operator_attestation_scope": "evidence_only",
        "created_at": "2026-06-24T09:00:00Z",
        "expires_at": "2026-06-24T12:00:00Z",
    }
    approval_policy = {
        "artifact_type": "approval_policy_fixture",
        "schema_version": "approval-policy-fixture.v1",
        "requires_manual_review": True,
        "requires_explicit_acknowledgment": True,
        "approval_scope": "evidence_only",
        "live_trading_approval": False,
        "live_submit_approval": False,
        "unattended_operation_allowed": False,
        "max_review_age_seconds": 3600,
        "expires_at": "2026-06-24T12:00:00Z",
    }
    kill_switch_observation = {
        "artifact_type": "kill_switch_observation_fixture",
        "schema_version": "kill-switch-observation-fixture.v1",
        "kill_switch_required": True,
        "observed_state": "blocked",
        "observed_at": "2026-06-24T10:00:00Z",
        "observation_source": "local_fixture",
        "override_attempted": False,
        "override_allowed": False,
        "default_on_missing": "blocked",
        "default_on_unknown": "blocked",
        "expires_at": "2026-06-24T12:00:00Z",
    }
    operator_acknowledgment = {
        "artifact_type": "operator_acknowledgment_fixture",
        "schema_version": "operator-acknowledgment-fixture.v1",
        "acknowledged_no_live_submit": True,
        "acknowledged_no_trading_authorization": True,
        "acknowledged_no_profitability_claim": True,
        "acknowledged_no_broker_certification": True,
        "acknowledged_review_is_evidence_only": True,
        "acknowledged_unattended_live_forbidden": True,
        "acknowledgment_text_digest": _ack_digest(),
        "acknowledged_at": "2026-06-24T10:00:00Z",
        "expires_at": "2026-06-24T12:00:00Z",
    }
    audit_policy = {
        "artifact_type": "audit_policy_fixture",
        "schema_version": "audit-policy-fixture.v1",
        "audit_required": True,
        "append_only_required": True,
        "hash_chain_required": True,
        "local_artifact_recording_required": True,
        "live_audit_chain_claimed": False,
        "expires_at": "2026-06-24T12:00:00Z",
    }
    paths = {}
    for name, data in [
        ("quality_gate", quality_gate),
        ("shadow_comparison", shadow_comparison),
        ("submit_conformance", submit_conformance),
        ("readiness_envelope", readiness_envelope),
        ("operator_identity", operator_identity),
        ("approval_policy", approval_policy),
        ("kill_switch_observation", kill_switch_observation),
        ("operator_acknowledgment", operator_acknowledgment),
        ("audit_policy", audit_policy),
    ]:
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        paths[name] = path
    return paths


def _base_args(paths: dict[str, Path], output_dir: Path) -> list[str]:
    return [
        "--quality-gate", str(paths["quality_gate"]),
        "--shadow-comparison", str(paths["shadow_comparison"]),
        "--submit-conformance", str(paths["submit_conformance"]),
        "--readiness-envelope", str(paths["readiness_envelope"]),
        "--operator-identity", str(paths["operator_identity"]),
        "--approval-policy", str(paths["approval_policy"]),
        "--kill-switch-observation", str(paths["kill_switch_observation"]),
        "--operator-acknowledgment", str(paths["operator_acknowledgment"]),
        "--audit-policy", str(paths["audit_policy"]),
        "--output-dir", str(output_dir),
        "--as-of", "2026-06-24T10:00:00Z",
    ]


def test_help_contains_disclaimer() -> None:
    assert "evidence-only" in CLI_DESCRIPTION.lower()
    assert "does not submit orders" in CLI_DESCRIPTION.lower()


def test_valid_cli_all_pass(tmp_path: Path) -> None:
    paths = _make_fixture_set(tmp_path)
    output_dir = tmp_path / "out"
    rc = main(_base_args(paths, output_dir))
    assert rc == 0
    assert (output_dir / "operator-approval-gate.json").is_file()


def test_json_output_mode(tmp_path: Path) -> None:
    paths = _make_fixture_set(tmp_path)
    output_dir = tmp_path / "out"
    rc = main(_base_args(paths, output_dir) + ["--json"])
    assert rc == 0


def test_missing_required_flag_fails(tmp_path: Path) -> None:
    paths = _make_fixture_set(tmp_path)
    args = _base_args(paths, tmp_path / "out")
    # Remove --quality-gate and its value.
    rc = main(args[2:])
    assert rc == 2


@pytest.mark.parametrize("flag", sorted(_UNSAFE_FLAGS))
def test_unsafe_flag_rejected(flag: str, tmp_path: Path) -> None:
    paths = _make_fixture_set(tmp_path)
    args = _base_args(paths, tmp_path / "out") + [flag]
    rc = main(args)
    assert rc == 2


def test_equals_syntax_rejected(tmp_path: Path) -> None:
    paths = _make_fixture_set(tmp_path)
    args = _base_args(paths, tmp_path / "out") + ["--mode=live"]
    rc = main(args)
    assert rc == 2


def test_workspace_before_agent_delegates_to_legacy() -> None:
    code = """
import io, sys
from atlas_agent.cli_bootstrap import main
old_stdout = sys.stdout
old_stderr = sys.stderr
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
try:
    main(["--workspace", "/tmp/nonexistent-ws-cand008", "agent", "operator-approval-gate", "--help"])
except SystemExit:
    pass
finally:
    sys.stdout = old_stdout
    sys.stderr = old_stderr
print("atlas_agent.cli" in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    output = result.stdout + result.stderr
    assert output.strip().splitlines()[-1] == "True", output


def test_workspace_after_agent_rejected_by_configless(tmp_path: Path) -> None:
    paths = _make_fixture_set(tmp_path)
    args = [
        "agent", "operator-approval-gate",
        "--workspace", str(tmp_path),
    ] + _base_args(paths, tmp_path / "out")[1:]
    rc = main(args)
    assert rc == 2


def test_output_path_aliasing_rejected(tmp_path: Path) -> None:
    paths = _make_fixture_set(tmp_path)
    aliased = tmp_path / "aliased_output"
    # Hard-link output dir to an input file.
    import os
    os.link(paths["quality_gate"], aliased)
    rc = main(_base_args(paths, aliased))
    assert rc == 2


def test_json_output_does_not_contain_input_paths(tmp_path: Path) -> None:
    paths = _make_fixture_set(tmp_path)
    output_dir = tmp_path / "out"
    rc = main(_base_args(paths, output_dir) + ["--json"])
    assert rc == 0
    json_text = (output_dir / "operator-approval-gate.json").read_text(encoding="utf-8")
    assert '"input_paths"' not in json_text


def test_json_output_does_not_leak_absolute_input_paths(tmp_path: Path) -> None:
    paths = _make_fixture_set(tmp_path)
    output_dir = tmp_path / "out"
    rc = main(_base_args(paths, output_dir) + ["--json"])
    assert rc == 0
    json_text = (output_dir / "operator-approval-gate.json").read_text(encoding="utf-8")
    for name, path in paths.items():
        assert str(path) not in json_text, f"absolute path leaked for {name}"
        assert str(path.parent) not in json_text, f"parent directory leaked for {name}"


def test_cli_json_stdout_does_not_contain_input_paths(tmp_path: Path, capsys: Any) -> None:
    paths = _make_fixture_set(tmp_path)
    output_dir = tmp_path / "out"
    rc = main(_base_args(paths, output_dir) + ["--json"])
    assert rc == 0
    captured = capsys.readouterr()
    assert '"input_paths"' not in captured.out
    assert '"input_paths"' not in captured.err
