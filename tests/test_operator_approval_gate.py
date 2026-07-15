# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_operator_approval_gate.py
# PURPOSE: Verifies operator approval gate behavior and regression expectations.
# DEPS:    hashlib, json, os, pathlib, typing, pytest, additional local modules.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from atlas_agent.agent.operator_approval_gate import (
    GATE_SEQUENCE,
    OperatorApprovalGateInputs,
    OperatorApprovalGateReport,
    OperatorApprovalGateValidationError,
    _CANONICAL_ACKNOWLEDGMENT_TEXT,
    _build_report,
    _compute_acknowledgment_digest,
    build_operator_approval_gate_report,
    fingerprint_json,
    parse_as_of_utc,
    write_operator_approval_gate_artifacts,
)


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _ack_digest() -> str:
    return _compute_acknowledgment_digest()


def _make_quality_gate(run_id: str = "run-123", symbol: str = "AAPL") -> dict:
    return {
        "artifact_type": "trading_quality_gate",
        "schema_version": "trading-quality-gate.v1",
        "mode": "paper",
        "run_id": run_id,
        "symbol": symbol,
        "quality_state": "eligible_for_shadow_live_quality_review",
        "blockers": [],
    }


def _make_shadow_comparison(run_id: str = "run-123", symbol: str = "AAPL") -> dict:
    return {
        "artifact_type": "shadow_live_comparison",
        "schema_version": "shadow-live-comparison.v1",
        "run_id": run_id,
        "symbol": symbol,
        "quality_state": "eligible_for_shadow_live_quality_review",
        "status": "matched",
        "freshness_assessment": {"snapshot_age_seconds": 0},
        "blockers": [],
    }


def _make_submit_conformance(
    run_id: str = "run-123", symbol: str = "AAPL", as_of: str = "2026-06-24T09:00:00Z"
) -> dict:
    return {
        "artifact_type": "gated_submit_conformance",
        "schema_version": "gated-submit-conformance.v1",
        "candidate": "CAND-006",
        "mode": "simulated_only",
        "run_id": run_id,
        "symbol": symbol,
        "status": "dry_run_recorded",
        "as_of": as_of,
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


def _make_readiness_envelope(
    run_id: str = "run-123", symbol: str = "AAPL", as_of: str = "2026-06-24T10:00:00Z"
) -> dict:
    return {
        "artifact_type": "runtime_readiness_envelope",
        "schema_version": "runtime-readiness-envelope.v1",
        "candidate": "CAND-007",
        "mode": "simulated_only",
        "status": "readiness_envelope_recorded",
        "exit_code": 0,
        "as_of": as_of,
        "run_id": run_id,
        "symbol": symbol,
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


def _make_operator_identity() -> dict:
    return {
        "artifact_type": "operator_identity_fixture",
        "schema_version": "operator-identity-fixture.v1",
        "operator_id": "operator-local-001",
        "operator_role": "local_evidence_reviewer",
        "operator_attestation_scope": "evidence_only",
        "created_at": "2026-06-24T09:00:00Z",
        "expires_at": "2026-06-24T12:00:00Z",
    }


def _make_approval_policy() -> dict:
    return {
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


def _make_kill_switch_observation() -> dict:
    return {
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


def _make_operator_acknowledgment() -> dict:
    return {
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


def _make_audit_policy() -> dict:
    return {
        "artifact_type": "audit_policy_fixture",
        "schema_version": "audit-policy-fixture.v1",
        "audit_required": True,
        "append_only_required": True,
        "hash_chain_required": True,
        "local_artifact_recording_required": True,
        "live_audit_chain_claimed": False,
        "expires_at": "2026-06-24T12:00:00Z",
    }


def _write_fixture(tmp_path: Path, name: str, data: dict) -> Path:
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _make_inputs(
    tmp_path: Path,
    *,
    quality_gate: dict | None = None,
    shadow_comparison: dict | None = None,
    submit_conformance: dict | None = None,
    readiness_envelope: dict | None = None,
    operator_identity: dict | None = None,
    approval_policy: dict | None = None,
    kill_switch_observation: dict | None = None,
    operator_acknowledgment: dict | None = None,
    audit_policy: dict | None = None,
    as_of: str = "2026-06-24T10:00:00Z",
) -> OperatorApprovalGateInputs:
    paths = {
        "quality_gate": _write_fixture(tmp_path, "quality_gate", quality_gate or _make_quality_gate()),
        "shadow_comparison": _write_fixture(tmp_path, "shadow_comparison", shadow_comparison or _make_shadow_comparison()),
        "submit_conformance": _write_fixture(tmp_path, "submit_conformance", submit_conformance or _make_submit_conformance()),
        "readiness_envelope": _write_fixture(tmp_path, "readiness_envelope", readiness_envelope or _make_readiness_envelope()),
        "operator_identity": _write_fixture(tmp_path, "operator_identity", operator_identity or _make_operator_identity()),
        "approval_policy": _write_fixture(tmp_path, "approval_policy", approval_policy or _make_approval_policy()),
        "kill_switch_observation": _write_fixture(tmp_path, "kill_switch_observation", kill_switch_observation or _make_kill_switch_observation()),
        "operator_acknowledgment": _write_fixture(tmp_path, "operator_acknowledgment", operator_acknowledgment or _make_operator_acknowledgment()),
        "audit_policy": _write_fixture(tmp_path, "audit_policy", audit_policy or _make_audit_policy()),
    }
    return OperatorApprovalGateInputs(
        output_dir=tmp_path / "out",
        as_of=as_of,
        quality_gate_path=paths["quality_gate"],
        shadow_comparison_path=paths["shadow_comparison"],
        submit_conformance_path=paths["submit_conformance"],
        readiness_envelope_path=paths["readiness_envelope"],
        operator_identity_path=paths["operator_identity"],
        approval_policy_path=paths["approval_policy"],
        kill_switch_observation_path=paths["kill_switch_observation"],
        operator_acknowledgment_path=paths["operator_acknowledgment"],
        audit_policy_path=paths["audit_policy"],
    )


def test_valid_all_pass_operator_gate(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "operator_gate_synthesized"
    assert report.exit_code == 2

    recorded = write_operator_approval_gate_artifacts(report, inputs.output_dir)
    assert recorded.status == "operator_gate_recorded"
    assert recorded.exit_code == 0
    assert (inputs.output_dir / "operator-approval-gate.json").is_file()
    assert (inputs.output_dir / "operator-approval-gate-report.md").is_file()


def test_missing_cand004_blocks(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    inputs.quality_gate_path.unlink()
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"
    assert report.gates[0].gate_id == "schema_preflight"
    assert report.gates[0].status == "fail"
    assert all(g.status == "not_run" for g in report.gates[1:])


def test_cand004_wrong_quality_state_blocks(tmp_path: Path) -> None:
    bad = _make_quality_gate()
    bad["quality_state"] = "not_eligible"
    inputs = _make_inputs(tmp_path, quality_gate=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "upstream_evidence_blocked"
    assert report.gates[1].gate_id == "cand004_projection_gate"
    assert report.gates[1].status == "fail"
    assert all(g.status == "not_run" for g in report.gates[2:])


def test_missing_cand005_blocks(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    inputs.shadow_comparison_path.unlink()
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_cand005_not_matched_blocks(tmp_path: Path) -> None:
    bad = _make_shadow_comparison()
    bad["status"] = "diverged"
    inputs = _make_inputs(tmp_path, shadow_comparison=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "upstream_evidence_blocked"
    assert report.gates[2].status == "fail"


def test_missing_cand006_blocks(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    inputs.submit_conformance_path.unlink()
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_cand006_status_not_dry_run_recorded_blocks(tmp_path: Path) -> None:
    bad = _make_submit_conformance()
    bad["status"] = "submitted"
    inputs = _make_inputs(tmp_path, submit_conformance=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "upstream_evidence_blocked"
    assert report.gates[3].status == "fail"


def test_cand006_blockers_non_empty_blocks(tmp_path: Path) -> None:
    bad = _make_submit_conformance()
    bad["blockers"] = ["something"]
    inputs = _make_inputs(tmp_path, submit_conformance=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "upstream_evidence_blocked"


def test_missing_cand007_blocks(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    inputs.readiness_envelope_path.unlink()
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_cand007_status_not_readiness_envelope_recorded_blocks(tmp_path: Path) -> None:
    bad = _make_readiness_envelope()
    bad["status"] = "blocked"
    inputs = _make_inputs(tmp_path, readiness_envelope=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "runtime_envelope_blocked"
    assert report.gates[4].status == "fail"


def test_cand007_blockers_non_empty_blocks(tmp_path: Path) -> None:
    bad = _make_readiness_envelope()
    bad["blockers"] = ["x"]
    inputs = _make_inputs(tmp_path, readiness_envelope=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "runtime_envelope_blocked"


def test_cand007_mode_not_simulated_only_blocks(tmp_path: Path) -> None:
    bad = _make_readiness_envelope()
    bad["mode"] = "live"
    inputs = _make_inputs(tmp_path, readiness_envelope=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_cand007_candidate_not_cand007_blocks(tmp_path: Path) -> None:
    bad = _make_readiness_envelope()
    bad["candidate"] = "CAND-999"
    inputs = _make_inputs(tmp_path, readiness_envelope=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_cand007_safety_assertion_false_blocks(tmp_path: Path) -> None:
    bad = _make_readiness_envelope()
    bad["envelope_assertions"]["live_submit_forbidden"] = False
    inputs = _make_inputs(tmp_path, readiness_envelope=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_cand007_operator_policy_fail_closed_false_blocks(tmp_path: Path) -> None:
    bad = _make_readiness_envelope()
    bad["envelope_assertions"]["operator_policy_fail_closed"] = False
    inputs = _make_inputs(tmp_path, readiness_envelope=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_cand007_all_upstream_statuses_accepted_false_blocks(tmp_path: Path) -> None:
    bad = _make_readiness_envelope()
    bad["envelope_assertions"]["all_upstream_statuses_accepted"] = False
    inputs = _make_inputs(tmp_path, readiness_envelope=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_cand007_cand006_transmission_blocked_false_blocks(tmp_path: Path) -> None:
    bad = _make_readiness_envelope()
    bad["envelope_assertions"]["cand006_transmission_blocked"] = False
    inputs = _make_inputs(tmp_path, readiness_envelope=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_run_id_mismatch_blocks(tmp_path: Path) -> None:
    bad = _make_shadow_comparison(run_id="run-999")
    inputs = _make_inputs(tmp_path, shadow_comparison=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "blocked"
    assert report.gates[5].status == "fail"


def test_symbol_mismatch_blocks(tmp_path: Path) -> None:
    bad = _make_shadow_comparison(symbol="TSLA")
    inputs = _make_inputs(tmp_path, shadow_comparison=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "blocked"
    assert report.gates[5].status == "fail"


def test_missing_operator_identity_blocks(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    inputs.operator_identity_path.unlink()
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_expired_operator_identity_blocks(tmp_path: Path) -> None:
    bad = _make_operator_identity()
    bad["expires_at"] = "2026-06-24T09:00:00Z"
    inputs = _make_inputs(tmp_path, operator_identity=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_operator_identity_unknown_field_blocks(tmp_path: Path) -> None:
    bad = _make_operator_identity()
    bad["extra_field"] = "x"
    inputs = _make_inputs(tmp_path, operator_identity=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_operator_identity_non_redacted_email_blocks(tmp_path: Path) -> None:
    bad = _make_operator_identity()
    bad["email"] = "operator@example.com"
    inputs = _make_inputs(tmp_path, operator_identity=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_approval_policy_live_trading_approval_true_blocks(tmp_path: Path) -> None:
    bad = _make_approval_policy()
    bad["live_trading_approval"] = True
    inputs = _make_inputs(tmp_path, approval_policy=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "approval_policy_blocked"


def test_approval_policy_live_submit_approval_true_blocks(tmp_path: Path) -> None:
    bad = _make_approval_policy()
    bad["live_submit_approval"] = True
    inputs = _make_inputs(tmp_path, approval_policy=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "approval_policy_blocked"


def test_approval_policy_unattended_allowed_blocks(tmp_path: Path) -> None:
    bad = _make_approval_policy()
    bad["unattended_operation_allowed"] = True
    inputs = _make_inputs(tmp_path, approval_policy=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "approval_policy_blocked"


def test_approval_policy_unknown_field_blocks(tmp_path: Path) -> None:
    bad = _make_approval_policy()
    bad["extra"] = 1
    inputs = _make_inputs(tmp_path, approval_policy=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_kill_switch_observation_unknown_blocks(tmp_path: Path) -> None:
    bad = _make_kill_switch_observation()
    bad["observed_state"] = "unknown"
    inputs = _make_inputs(tmp_path, kill_switch_observation=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "kill_switch_observation_blocked"


def test_kill_switch_observation_inactive_blocks(tmp_path: Path) -> None:
    bad = _make_kill_switch_observation()
    bad["observed_state"] = "inactive"
    inputs = _make_inputs(tmp_path, kill_switch_observation=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "kill_switch_observation_blocked"


def test_kill_switch_override_attempted_blocks(tmp_path: Path) -> None:
    bad = _make_kill_switch_observation()
    bad["override_attempted"] = True
    inputs = _make_inputs(tmp_path, kill_switch_observation=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "kill_switch_observation_blocked"


def test_kill_switch_override_allowed_true_blocks(tmp_path: Path) -> None:
    bad = _make_kill_switch_observation()
    bad["override_allowed"] = True
    inputs = _make_inputs(tmp_path, kill_switch_observation=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "kill_switch_observation_blocked"


def test_kill_switch_default_on_missing_not_blocked_blocks(tmp_path: Path) -> None:
    bad = _make_kill_switch_observation()
    bad["default_on_missing"] = "inactive"
    inputs = _make_inputs(tmp_path, kill_switch_observation=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_kill_switch_default_on_unknown_not_blocked_blocks(tmp_path: Path) -> None:
    bad = _make_kill_switch_observation()
    bad["default_on_unknown"] = "unknown"
    inputs = _make_inputs(tmp_path, kill_switch_observation=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_operator_acknowledgment_missing_no_live_submit_blocks(tmp_path: Path) -> None:
    bad = _make_operator_acknowledgment()
    bad["acknowledged_no_live_submit"] = False
    inputs = _make_inputs(tmp_path, operator_acknowledgment=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_operator_acknowledgment_missing_no_trading_authorization_blocks(tmp_path: Path) -> None:
    bad = _make_operator_acknowledgment()
    bad["acknowledged_no_trading_authorization"] = False
    inputs = _make_inputs(tmp_path, operator_acknowledgment=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_operator_acknowledgment_digest_mismatch_blocks(tmp_path: Path) -> None:
    bad = _make_operator_acknowledgment()
    bad["acknowledgment_text_digest"] = "sha256:" + "0" * 64
    inputs = _make_inputs(tmp_path, operator_acknowledgment=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_audit_policy_invalid_blocks(tmp_path: Path) -> None:
    bad = _make_audit_policy()
    bad["live_audit_chain_claimed"] = True
    inputs = _make_inputs(tmp_path, audit_policy=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "audit_policy_blocked"


def test_secret_like_fields_rejected(tmp_path: Path) -> None:
    bad = _make_operator_identity()
    bad["api_key"] = "secret"
    inputs = _make_inputs(tmp_path, operator_identity=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_endpoint_like_fields_rejected(tmp_path: Path) -> None:
    bad = _make_approval_policy()
    bad["endpoint"] = "https://example.com"
    inputs = _make_inputs(tmp_path, approval_policy=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_url_protocol_values_rejected(tmp_path: Path) -> None:
    bad = _make_audit_policy()
    bad["notes"] = "contact https://example.com"
    inputs = _make_inputs(tmp_path, audit_policy=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_raw_artifact_leakage_rejected(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report = build_operator_approval_gate_report(inputs)
    recorded = write_operator_approval_gate_artifacts(report, inputs.output_dir)
    json_text = (inputs.output_dir / "operator-approval-gate.json").read_text(
        encoding="utf-8"
    )
    # Upstream raw keys should not appear.
    assert "dry_run_request" not in json_text
    assert "envelope_assertions" not in json_text
    assert recorded.status == "operator_gate_recorded"


def test_output_path_aliasing_rejected(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    # Make output_dir the same file as an input by using a hard link.
    aliased_output = tmp_path / "aliased_out"
    os.link(inputs.quality_gate_path, aliased_output)
    inputs = OperatorApprovalGateInputs(
        quality_gate_path=inputs.quality_gate_path,
        shadow_comparison_path=inputs.shadow_comparison_path,
        submit_conformance_path=inputs.submit_conformance_path,
        readiness_envelope_path=inputs.readiness_envelope_path,
        operator_identity_path=inputs.operator_identity_path,
        approval_policy_path=inputs.approval_policy_path,
        kill_switch_observation_path=inputs.kill_switch_observation_path,
        operator_acknowledgment_path=inputs.operator_acknowledgment_path,
        audit_policy_path=inputs.audit_policy_path,
        output_dir=aliased_output,
        as_of=inputs.as_of,
    )
    report = build_operator_approval_gate_report(inputs)
    recorded = write_operator_approval_gate_artifacts(report, aliased_output)
    assert recorded.status == "blocked"
    assert recorded.gates[-1].status == "fail"


def test_json_and_markdown_agree(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report = build_operator_approval_gate_report(inputs)
    recorded = write_operator_approval_gate_artifacts(report, inputs.output_dir)
    json_data = json.loads(
        (inputs.output_dir / "operator-approval-gate.json").read_text(encoding="utf-8")
    )
    md_text = (inputs.output_dir / "operator-approval-gate-report.md").read_text(
        encoding="utf-8"
    )
    assert json_data["status"] == recorded.status
    assert json_data["evaluation_id"] == recorded.evaluation_id
    assert recorded.disclaimer in md_text


def test_json_write_failure_rolls_back_status(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report = build_operator_approval_gate_report(inputs)
    # Use a regular file as the output directory so mkdir fails.
    bad_output = tmp_path / "blocked_output"
    bad_output.write_text("x", encoding="utf-8")
    recorded = write_operator_approval_gate_artifacts(report, bad_output)
    assert recorded.status == "blocked"


def test_synthesis_failure_returns_blocked(tmp_path: Path, monkeypatch: Any) -> None:
    original_build_report = _build_report

    def _failing_build_report(*args: Any, **kwargs: Any) -> OperatorApprovalGateReport:
        if kwargs.get("status") == "operator_gate_synthesized":
            raise RuntimeError("simulated synthesis failure")
        return original_build_report(*args, **kwargs)

    monkeypatch.setattr(
        "atlas_agent.agent.operator_approval_gate._build_report", _failing_build_report
    )

    inputs = _make_inputs(tmp_path)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "blocked"
    assert report.exit_code == 2
    synthesis_gate = next(g for g in report.gates if g.gate_id == "approval_gate_synthesis")
    assert synthesis_gate.status == "fail"
    assert "simulated synthesis failure" in synthesis_gate.reason
    recording_gate = next(g for g in report.gates if g.gate_id == "artifact_recording_gate")
    assert recording_gate.status == "not_run"
    assert report.status != "operator_gate_synthesized"


def test_operator_gate_synthesized_is_not_final_success(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "operator_gate_synthesized"
    assert report.exit_code == 2


def test_only_operator_gate_recorded_exits_zero(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report = build_operator_approval_gate_report(inputs)
    recorded = write_operator_approval_gate_artifacts(report, inputs.output_dir)
    assert recorded.status == "operator_gate_recorded"
    assert recorded.exit_code == 0


def test_disclaimer_present_in_json_and_markdown(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report = build_operator_approval_gate_report(inputs)
    recorded = write_operator_approval_gate_artifacts(report, inputs.output_dir)
    json_text = (inputs.output_dir / "operator-approval-gate.json").read_text(
        encoding="utf-8"
    )
    md_text = (inputs.output_dir / "operator-approval-gate-report.md").read_text(
        encoding="utf-8"
    )
    assert "evidence-recording status only" in json_text
    assert "evidence-recording status only" in md_text


def test_literal_acknowledgment_text_not_emitted(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report = build_operator_approval_gate_report(inputs)
    recorded = write_operator_approval_gate_artifacts(report, inputs.output_dir)
    json_text = (inputs.output_dir / "operator-approval-gate.json").read_text(
        encoding="utf-8"
    )
    assert _CANONICAL_ACKNOWLEDGMENT_TEXT not in json_text
    assert recorded.status == "operator_gate_recorded"


def test_first_failure_gate_ordering(tmp_path: Path) -> None:
    bad = _make_quality_gate()
    bad["mode"] = "live"
    inputs = _make_inputs(tmp_path, quality_gate=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.gates[1].status == "fail"
    assert report.gates[1].gate_id == "cand004_projection_gate"
    for gate in report.gates[2:]:
        assert gate.status == "not_run"


def test_downstream_gates_not_run_after_failure(tmp_path: Path) -> None:
    bad = _make_approval_policy()
    bad["live_submit_approval"] = True
    inputs = _make_inputs(tmp_path, approval_policy=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "approval_policy_blocked"
    # operator_identity_gate and prior gates passed; approval_policy_gate failed.
    failed_idx = next(i for i, g in enumerate(report.gates) if g.gate_id == "approval_policy_gate")
    for gate in report.gates[failed_idx + 1 :]:
        assert gate.status == "not_run"


def test_input_digest_stable(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report1 = build_operator_approval_gate_report(inputs)
    report2 = build_operator_approval_gate_report(inputs)
    assert report1.input_digest == report2.input_digest


def test_fingerprint_changes_when_fixture_changes(tmp_path: Path) -> None:
    inputs1 = _make_inputs(tmp_path)
    report1 = build_operator_approval_gate_report(inputs1)
    bad = _make_operator_identity()
    bad["operator_id"] = "different"
    inputs2 = _make_inputs(tmp_path, operator_identity=bad)
    report2 = build_operator_approval_gate_report(inputs2)
    assert report1.input_fingerprints["operator_identity"] != report2.input_fingerprints["operator_identity"]


def test_cand006_evidence_age_blocks(tmp_path: Path) -> None:
    bad = _make_submit_conformance(as_of="2026-06-20T09:00:00Z")
    inputs = _make_inputs(tmp_path, submit_conformance=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_cand006_as_of_after_cand008_blocks(tmp_path: Path) -> None:
    bad = _make_submit_conformance(as_of="2026-06-24T11:00:00Z")
    inputs = _make_inputs(tmp_path, submit_conformance=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_cand007_evidence_age_blocks(tmp_path: Path) -> None:
    bad = _make_readiness_envelope(as_of="2026-06-20T10:00:00Z")
    inputs = _make_inputs(tmp_path, readiness_envelope=bad)
    report = build_operator_approval_gate_report(inputs)
    assert report.status == "not_evaluated"


def test_parse_as_of_utc_rejects_naive() -> None:
    with pytest.raises(OperatorApprovalGateValidationError):
        parse_as_of_utc("2026-06-24T10:00:00")


def test_parse_as_of_utc_accepts_z_and_offset() -> None:
    assert parse_as_of_utc("2026-06-24T10:00:00Z") == "2026-06-24T10:00:00Z"
    assert parse_as_of_utc("2026-06-24T10:00:00+00:00") == "2026-06-24T10:00:00Z"


def test_json_artifact_does_not_contain_input_paths_key(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report = build_operator_approval_gate_report(inputs)
    recorded = write_operator_approval_gate_artifacts(report, inputs.output_dir)
    json_text = (inputs.output_dir / "operator-approval-gate.json").read_text(
        encoding="utf-8"
    )
    assert '"input_paths"' not in json_text
    assert recorded.status == "operator_gate_recorded"


def test_json_artifact_does_not_leak_absolute_input_paths(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report = build_operator_approval_gate_report(inputs)
    recorded = write_operator_approval_gate_artifacts(report, inputs.output_dir)
    json_text = (inputs.output_dir / "operator-approval-gate.json").read_text(
        encoding="utf-8"
    )
    for label in [
        "quality_gate",
        "shadow_comparison",
        "submit_conformance",
        "readiness_envelope",
        "operator_identity",
        "approval_policy",
        "kill_switch_observation",
        "operator_acknowledgment",
        "audit_policy",
    ]:
        path = getattr(inputs, f"{label}_path")
        assert str(path) not in json_text, f"absolute path leaked for {label}"
        assert str(path.parent) not in json_text, f"parent directory leaked for {label}"
    assert recorded.status == "operator_gate_recorded"


def test_markdown_artifact_does_not_leak_absolute_input_paths(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report = build_operator_approval_gate_report(inputs)
    recorded = write_operator_approval_gate_artifacts(report, inputs.output_dir)
    md_text = (inputs.output_dir / "operator-approval-gate-report.md").read_text(
        encoding="utf-8"
    )
    for label in [
        "quality_gate",
        "shadow_comparison",
        "submit_conformance",
        "readiness_envelope",
        "operator_identity",
        "approval_policy",
        "kill_switch_observation",
        "operator_acknowledgment",
        "audit_policy",
    ]:
        path = getattr(inputs, f"{label}_path")
        assert str(path) not in md_text, f"absolute path leaked for {label}"
        assert str(path.parent) not in md_text, f"parent directory leaked for {label}"
    assert recorded.status == "operator_gate_recorded"


def test_input_artifacts_contains_only_safe_basenames(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report = build_operator_approval_gate_report(inputs)
    recorded = write_operator_approval_gate_artifacts(report, inputs.output_dir)
    for label, name in recorded.input_artifacts.items():
        assert name is not None
        assert "/" not in name
        assert "\\" not in name
        assert name == getattr(inputs, f"{label}_path").name


def test_input_fingerprints_remain_deterministic(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report1 = build_operator_approval_gate_report(inputs)
    report2 = build_operator_approval_gate_report(inputs)
    assert report1.input_fingerprints == report2.input_fingerprints
    assert report1.input_fingerprints
    for label in report1.input_fingerprints:
        assert report1.input_fingerprints[label].startswith("sha256:")
