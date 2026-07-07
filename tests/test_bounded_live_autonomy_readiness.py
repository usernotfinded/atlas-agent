from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from atlas_agent.agent.bounded_live_autonomy_readiness import (
    GATE_SEQUENCE,
    APPROVED_FINAL_STATUSES,
    BoundedLiveAutonomyReadinessInputs,
    BoundedLiveAutonomyReadinessReport,
    BoundedLiveAutonomyReadinessValidationError,
    _build_readiness_assertions,
    build_bounded_live_autonomy_readiness_report,
    fingerprint_json,
    parse_as_of_utc,
    write_bounded_live_autonomy_readiness_artifacts,
)


def _make_quality_gate(run_id: str = "run-cand015-001", symbol: str = "AAPL") -> dict:
    return {
        "artifact_type": "trading_quality_gate",
        "schema_version": "trading-quality-gate.v1",
        "mode": "paper",
        "run_id": run_id,
        "symbol": symbol,
        "quality_state": "eligible_for_shadow_live_quality_review",
        "blockers": [],
    }


def _make_shadow_comparison(run_id: str = "run-cand015-001", symbol: str = "AAPL") -> dict:
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
    run_id: str = "run-cand015-001", symbol: str = "AAPL", as_of: str = "2026-06-24T09:00:00Z"
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
    run_id: str = "run-cand015-001", symbol: str = "AAPL", as_of: str = "2026-06-24T10:00:00Z"
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


def _make_operator_approval_gate(
    run_id: str = "run-cand015-001", symbol: str = "AAPL", as_of: str = "2026-06-24T10:30:00Z"
) -> dict:
    return {
        "artifact_type": "operator_approval_gate",
        "schema_version": "operator-approval-gate.v1",
        "candidate": "CAND-008",
        "mode": "evidence_only",
        "status": "operator_gate_recorded",
        "exit_code": 0,
        "as_of": as_of,
        "run_id": run_id,
        "symbol": symbol,
        "blockers": [],
        "approval_gate_assertions": {
            "cand007_status_accepted": True,
            "cand007_mode_simulated_only": True,
            "cand007_blockers_empty": True,
            "cand007_safety_assertions_accepted": True,
            "operator_identity_valid": True,
            "approval_policy_fail_closed": True,
            "kill_switch_observed_blocked": True,
            "operator_acknowledgments_all_true": True,
            "audit_policy_fail_closed": True,
            "no_credentials_in_fixtures": True,
            "no_endpoints_in_fixtures": True,
            "no_account_ids_in_fixtures": True,
            "no_raw_upstream_leakage": True,
        },
    }


def _make_bounded_autonomy_policy() -> dict:
    return {
        "artifact_type": "bounded_autonomy_policy_fixture",
        "schema_version": "bounded-autonomy-policy-fixture.v1",
        "policy_scope": "l2_l3_readiness_evaluation",
        "l3_autonomy_enabled": False,
        "live_submit_enabled_by_default": False,
        "provider_output_authoritative": False,
        "manual_approval_required": True,
        "unattended_operation_allowed": False,
        "auto_approval_allowed": False,
        "requires_explicit_opt_in": True,
        "requires_active_operator_oversight": True,
        "requires_paper_validation": True,
        "min_paper_validation_runs": 3,
        "expires_at": "2026-06-24T14:00:00Z",
    }


def _make_risk_limit() -> dict:
    return {
        "artifact_type": "risk_limit_fixture",
        "schema_version": "risk-limit-fixture.v1",
        "max_single_order_notional": "1000.00",
        "max_position_notional_per_symbol": "5000.00",
        "max_total_net_exposure_pct": "5.0",
        "max_daily_loss_notional": "500.00",
        "max_orders_per_interval": 10,
        "quote_freshness_required_seconds": 5,
        "allowed_sides": ["buy"],
        "allowed_order_types": ["limit"],
        "leverage_allowed": False,
        "shorting_allowed": False,
        "options_allowed": False,
        "expires_at": "2026-06-24T14:00:00Z",
    }


def _make_symbol_allowlist() -> dict:
    return {
        "artifact_type": "symbol_allowlist_fixture",
        "schema_version": "symbol-allowlist-fixture.v1",
        "allowlist_mode": "explicit_allowlist",
        "allowed_symbols": ["AAPL"],
        "blocked_symbols": [],
        "allow_empty_blocklist": True,
        "expires_at": "2026-06-24T14:00:00Z",
    }


def _make_heartbeat_deadman() -> dict:
    return {
        "artifact_type": "heartbeat_deadman_fixture",
        "schema_version": "heartbeat-deadman-fixture.v1",
        "heartbeat_required": True,
        "heartbeat_interval_seconds": 30,
        "deadman_required": True,
        "deadman_ttl_seconds": 120,
        "missing_heartbeat_fails_closed": True,
        "stale_heartbeat_fails_closed": True,
        "expires_at": "2026-06-24T14:00:00Z",
    }


def _make_audit_redaction() -> dict:
    return {
        "artifact_type": "audit_redaction_fixture",
        "schema_version": "audit-redaction-fixture.v1",
        "redacts_secrets": True,
        "redacts_api_keys": True,
        "redacts_account_ids": True,
        "redacts_raw_broker_payloads": True,
        "redacts_raw_provider_output": True,
        "redacts_paths": True,
        "redacts_exception_text": True,
        "audit_hash_chain_required": True,
        "manifest_required": True,
        "expires_at": "2026-06-24T14:00:00Z",
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
    operator_approval_gate: dict | None = None,
    bounded_autonomy_policy: dict | None = None,
    risk_limit: dict | None = None,
    symbol_allowlist: dict | None = None,
    heartbeat_deadman: dict | None = None,
    audit_redaction: dict | None = None,
    as_of: str = "2026-06-24T11:00:00Z",
) -> BoundedLiveAutonomyReadinessInputs:
    paths = {
        "quality_gate": _write_fixture(tmp_path, "quality_gate", quality_gate or _make_quality_gate()),
        "shadow_comparison": _write_fixture(tmp_path, "shadow_comparison", shadow_comparison or _make_shadow_comparison()),
        "submit_conformance": _write_fixture(tmp_path, "submit_conformance", submit_conformance or _make_submit_conformance()),
        "readiness_envelope": _write_fixture(tmp_path, "readiness_envelope", readiness_envelope or _make_readiness_envelope()),
        "operator_approval_gate": _write_fixture(tmp_path, "operator_approval_gate", operator_approval_gate or _make_operator_approval_gate()),
        "bounded_autonomy_policy": _write_fixture(tmp_path, "bounded_autonomy_policy", bounded_autonomy_policy or _make_bounded_autonomy_policy()),
        "risk_limit": _write_fixture(tmp_path, "risk_limit", risk_limit or _make_risk_limit()),
        "symbol_allowlist": _write_fixture(tmp_path, "symbol_allowlist", symbol_allowlist or _make_symbol_allowlist()),
        "heartbeat_deadman": _write_fixture(tmp_path, "heartbeat_deadman", heartbeat_deadman or _make_heartbeat_deadman()),
        "audit_redaction": _write_fixture(tmp_path, "audit_redaction", audit_redaction or _make_audit_redaction()),
    }
    return BoundedLiveAutonomyReadinessInputs(
        output_dir=tmp_path / "out",
        as_of=as_of,
        quality_gate_path=paths["quality_gate"],
        shadow_comparison_path=paths["shadow_comparison"],
        submit_conformance_path=paths["submit_conformance"],
        readiness_envelope_path=paths["readiness_envelope"],
        operator_approval_gate_path=paths["operator_approval_gate"],
        bounded_autonomy_policy_path=paths["bounded_autonomy_policy"],
        risk_limit_path=paths["risk_limit"],
        symbol_allowlist_path=paths["symbol_allowlist"],
        heartbeat_deadman_path=paths["heartbeat_deadman"],
        audit_redaction_path=paths["audit_redaction"],
    )


def test_valid_all_pass(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "readiness_synthesized"
    assert report.exit_code == 0

    recorded = write_bounded_live_autonomy_readiness_artifacts(report, inputs.output_dir)
    assert recorded.status == "bounded_live_readiness_recorded"
    assert recorded.exit_code == 0
    assert (inputs.output_dir / "bounded-live-readiness.json").is_file()
    assert (inputs.output_dir / "bounded-live-readiness-report.md").is_file()


def test_missing_cand004_blocks(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    inputs.quality_gate_path.unlink()
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "blocked"
    assert report.gates[0].gate_id == "schema_preflight"
    assert report.gates[0].status == "fail"
    assert all(g.status == "not_run" for g in report.gates[1:])


def test_cand004_blockers_non_empty_blocks(tmp_path: Path) -> None:
    bad = _make_quality_gate()
    bad["blockers"] = ["quality issue"]
    inputs = _make_inputs(tmp_path, quality_gate=bad)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "blocked"
    assert report.gates[1].gate_id == "cand004_projection_gate"
    assert report.gates[1].status == "fail"


def test_cand006_transmission_allowed_blocks(tmp_path: Path) -> None:
    bad = _make_submit_conformance()
    bad["dry_run_request"]["transmission"]["allowed"] = True
    inputs = _make_inputs(tmp_path, submit_conformance=bad)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "blocked"
    assert report.gates[3].status == "fail"


def test_cand007_mode_not_simulated_only_blocks(tmp_path: Path) -> None:
    bad = _make_readiness_envelope()
    bad["mode"] = "live"
    inputs = _make_inputs(tmp_path, readiness_envelope=bad)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "blocked"


def test_cand008_candidate_wrong_blocks(tmp_path: Path) -> None:
    bad = _make_operator_approval_gate()
    bad["candidate"] = "CAND-999"
    inputs = _make_inputs(tmp_path, operator_approval_gate=bad)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "blocked"


def test_run_id_mismatch_blocks(tmp_path: Path) -> None:
    bad = _make_shadow_comparison(run_id="run-999")
    inputs = _make_inputs(tmp_path, shadow_comparison=bad)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "blocked"
    assert report.gates[6].gate_id == "cross_artifact_correlation_gate"
    assert report.gates[6].status == "fail"


def test_symbol_mismatch_blocks(tmp_path: Path) -> None:
    bad = _make_shadow_comparison(symbol="TSLA")
    inputs = _make_inputs(tmp_path, shadow_comparison=bad)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "blocked"


def test_l3_autonomy_enabled_blocks(tmp_path: Path) -> None:
    bad = _make_bounded_autonomy_policy()
    bad["l3_autonomy_enabled"] = True
    inputs = _make_inputs(tmp_path, bounded_autonomy_policy=bad)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "blocked"
    assert report.gates[7].gate_id == "bounded_autonomy_policy_gate"
    assert report.gates[7].status == "fail"


def test_live_submit_enabled_by_default_blocks(tmp_path: Path) -> None:
    bad = _make_bounded_autonomy_policy()
    bad["live_submit_enabled_by_default"] = True
    inputs = _make_inputs(tmp_path, bounded_autonomy_policy=bad)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "blocked"


def test_provider_output_authoritative_blocks(tmp_path: Path) -> None:
    bad = _make_bounded_autonomy_policy()
    bad["provider_output_authoritative"] = True
    inputs = _make_inputs(tmp_path, bounded_autonomy_policy=bad)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "blocked"
    assert report.gates[7].gate_id == "bounded_autonomy_policy_gate"
    assert report.gates[7].status == "fail"
    failures = report.gates[7].details.get("failures", [])
    assert any("provider_output_authoritative" in f for f in failures)


def test_leverage_allowed_blocks(tmp_path: Path) -> None:
    bad = _make_risk_limit()
    bad["leverage_allowed"] = True
    inputs = _make_inputs(tmp_path, risk_limit=bad)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "blocked"
    assert report.gates[8].gate_id == "risk_limit_gate"
    assert report.gates[8].status == "fail"


def test_empty_notional_limit_blocks(tmp_path: Path) -> None:
    bad = _make_risk_limit()
    bad["max_single_order_notional"] = "0.00"
    inputs = _make_inputs(tmp_path, risk_limit=bad)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "blocked"
    assert report.gates[0].gate_id == "schema_preflight"
    assert report.gates[0].status == "fail"


def test_empty_allowed_sides_blocks(tmp_path: Path) -> None:
    bad = _make_risk_limit()
    bad["allowed_sides"] = []
    inputs = _make_inputs(tmp_path, risk_limit=bad)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "blocked"
    assert report.gates[0].status == "fail"


def test_empty_allowed_order_types_blocks(tmp_path: Path) -> None:
    bad = _make_risk_limit()
    bad["allowed_order_types"] = []
    inputs = _make_inputs(tmp_path, risk_limit=bad)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "blocked"
    assert report.gates[0].status == "fail"


def test_symbol_not_in_allowlist_blocks(tmp_path: Path) -> None:
    allowlist = _make_symbol_allowlist()
    allowlist["allowed_symbols"] = ["AAPL"]
    inputs = _make_inputs(tmp_path, symbol_allowlist=allowlist)
    bad = _make_quality_gate(symbol="TSLA")
    inputs.quality_gate_path.write_text(json.dumps(bad), encoding="utf-8")
    # Keep upstream artifacts symbol-aligned with the changed quality gate.
    for label in ("shadow_comparison", "submit_conformance", "readiness_envelope", "operator_approval_gate"):
        path = getattr(inputs, f"{label}_path")
        data = json.loads(path.read_text(encoding="utf-8"))
        data["symbol"] = "TSLA"
        path.write_text(json.dumps(data), encoding="utf-8")
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "blocked"
    assert report.gates[9].status == "fail"


def test_symbol_blocked_blocks(tmp_path: Path) -> None:
    bad = _make_symbol_allowlist()
    bad["blocked_symbols"] = ["AAPL"]
    inputs = _make_inputs(tmp_path, symbol_allowlist=bad)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "blocked"


def test_missing_heartbeat_fails_closed_false_blocks(tmp_path: Path) -> None:
    bad = _make_heartbeat_deadman()
    bad["missing_heartbeat_fails_closed"] = False
    inputs = _make_inputs(tmp_path, heartbeat_deadman=bad)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "blocked"
    assert report.gates[10].status == "fail"


def test_audit_missing_manifest_blocks(tmp_path: Path) -> None:
    bad = _make_audit_redaction()
    bad["manifest_required"] = False
    inputs = _make_inputs(tmp_path, audit_redaction=bad)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "blocked"
    assert report.gates[11].status == "fail"


def test_fixture_with_forbidden_key_blocks(tmp_path: Path) -> None:
    bad = _make_bounded_autonomy_policy()
    bad["broker"] = "alpaca"
    inputs = _make_inputs(tmp_path, bounded_autonomy_policy=bad)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "blocked"


def test_fixture_with_secret_value_blocks(tmp_path: Path) -> None:
    bad = _make_risk_limit()
    bad["notes"] = "token ghp_1234567890"
    inputs = _make_inputs(tmp_path, risk_limit=bad)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "blocked"


def test_downstream_gates_not_run_after_failure(tmp_path: Path) -> None:
    bad = _make_bounded_autonomy_policy()
    bad["auto_approval_allowed"] = True
    inputs = _make_inputs(tmp_path, bounded_autonomy_policy=bad)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    failed_idx = next(i for i, g in enumerate(report.gates) if g.gate_id == "bounded_autonomy_policy_gate")
    for gate in report.gates[failed_idx + 1 :]:
        assert gate.status == "not_run"


def test_input_digest_stable(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report1 = build_bounded_live_autonomy_readiness_report(inputs)
    report2 = build_bounded_live_autonomy_readiness_report(inputs)
    assert report1.input_digest == report2.input_digest


def test_fingerprint_changes_when_fixture_changes(tmp_path: Path) -> None:
    inputs1 = _make_inputs(tmp_path)
    report1 = build_bounded_live_autonomy_readiness_report(inputs1)
    bad = _make_risk_limit()
    bad["max_single_order_notional"] = "2000.00"
    inputs2 = _make_inputs(tmp_path, risk_limit=bad)
    report2 = build_bounded_live_autonomy_readiness_report(inputs2)
    assert report1.input_fingerprints["risk_limit"] != report2.input_fingerprints["risk_limit"]


def test_evidence_age_blocks(tmp_path: Path) -> None:
    bad = _make_submit_conformance(as_of="2026-06-20T09:00:00Z")
    inputs = _make_inputs(tmp_path, submit_conformance=bad)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "blocked"


def test_submit_conformance_as_of_after_cand015_blocks(tmp_path: Path) -> None:
    bad = _make_submit_conformance(as_of="2026-06-24T12:00:00Z")
    inputs = _make_inputs(tmp_path, submit_conformance=bad)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    assert report.status == "blocked"


def test_parse_as_of_utc_rejects_naive() -> None:
    with pytest.raises(BoundedLiveAutonomyReadinessValidationError):
        parse_as_of_utc("2026-06-24T11:00:00")


def test_parse_as_of_utc_accepts_z_and_offset() -> None:
    assert parse_as_of_utc("2026-06-24T11:00:00Z") == "2026-06-24T11:00:00Z"
    assert parse_as_of_utc("2026-06-24T11:00:00+00:00") == "2026-06-24T11:00:00Z"


def test_json_artifact_does_not_contain_input_paths(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    recorded = write_bounded_live_autonomy_readiness_artifacts(report, inputs.output_dir)
    json_text = (inputs.output_dir / "bounded-live-readiness.json").read_text(encoding="utf-8")
    assert '"input_paths"' not in json_text
    assert recorded.status == "bounded_live_readiness_recorded"


def test_json_artifact_does_not_leak_absolute_input_paths(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    recorded = write_bounded_live_autonomy_readiness_artifacts(report, inputs.output_dir)
    json_text = (inputs.output_dir / "bounded-live-readiness.json").read_text(encoding="utf-8")
    for label in [
        "quality_gate",
        "shadow_comparison",
        "submit_conformance",
        "readiness_envelope",
        "operator_approval_gate",
        "bounded_autonomy_policy",
        "risk_limit",
        "symbol_allowlist",
        "heartbeat_deadman",
        "audit_redaction",
    ]:
        path = getattr(inputs, f"{label}_path")
        assert str(path) not in json_text, f"absolute path leaked for {label}"
        assert str(path.parent) not in json_text, f"parent directory leaked for {label}"
    assert recorded.status == "bounded_live_readiness_recorded"


def test_input_artifacts_contains_only_safe_basenames(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    recorded = write_bounded_live_autonomy_readiness_artifacts(report, inputs.output_dir)
    for label, name in recorded.input_artifacts.items():
        assert name is not None
        assert "/" not in name
        assert "\\" not in name
        assert name == getattr(inputs, f"{label}_path").name


def test_disclaimer_present_in_json_and_markdown(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    recorded = write_bounded_live_autonomy_readiness_artifacts(report, inputs.output_dir)
    json_text = (inputs.output_dir / "bounded-live-readiness.json").read_text(encoding="utf-8")
    md_text = (inputs.output_dir / "bounded-live-readiness-report.md").read_text(encoding="utf-8")
    assert "evidence-recording status only" in json_text
    assert "evidence-recording status only" in md_text
    assert recorded.status == "bounded_live_readiness_recorded"


def test_output_path_aliasing_rejected(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    aliased_output = tmp_path / "aliased_out"
    os.link(inputs.quality_gate_path, aliased_output)
    inputs = BoundedLiveAutonomyReadinessInputs(
        quality_gate_path=inputs.quality_gate_path,
        shadow_comparison_path=inputs.shadow_comparison_path,
        submit_conformance_path=inputs.submit_conformance_path,
        readiness_envelope_path=inputs.readiness_envelope_path,
        operator_approval_gate_path=inputs.operator_approval_gate_path,
        bounded_autonomy_policy_path=inputs.bounded_autonomy_policy_path,
        risk_limit_path=inputs.risk_limit_path,
        symbol_allowlist_path=inputs.symbol_allowlist_path,
        heartbeat_deadman_path=inputs.heartbeat_deadman_path,
        audit_redaction_path=inputs.audit_redaction_path,
        output_dir=aliased_output,
        as_of=inputs.as_of,
    )
    report = build_bounded_live_autonomy_readiness_report(inputs)
    recorded = write_bounded_live_autonomy_readiness_artifacts(report, aliased_output)
    assert recorded.status == "blocked"


def test_json_write_failure_rolls_back_status(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report = build_bounded_live_autonomy_readiness_report(inputs)
    bad_output = tmp_path / "blocked_output"
    bad_output.write_text("x", encoding="utf-8")
    recorded = write_bounded_live_autonomy_readiness_artifacts(report, bad_output)
    assert recorded.status == "blocked"


def test_gate_sequence_constant_complete() -> None:
    assert len(GATE_SEQUENCE) == 15
    assert GATE_SEQUENCE[0] == "schema_preflight"
    assert GATE_SEQUENCE[-1] == "artifact_recording_gate"


def test_approved_final_statuses_include_recorded_and_blocked() -> None:
    assert "bounded_live_readiness_recorded" in APPROVED_FINAL_STATUSES
    assert "blocked" in APPROVED_FINAL_STATUSES
