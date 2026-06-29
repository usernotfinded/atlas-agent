from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from atlas_agent.agent.runtime_readiness_envelope import (
    APPROVED_FINAL_STATUSES,
    GATE_SEQUENCE,
    EVIDENCE_ONLY_DISCLAIMER,
    ReadinessEnvelopeInputs,
    canonical_json_bytes,
    fingerprint_json,
    parse_as_of_utc,
    build_runtime_readiness_envelope_report,
    _validate_quality_gate,
    _validate_shadow_comparison,
    _validate_submit_conformance,
    _validate_runtime_envelope_fixture,
    _validate_broker_capability_manifest,
    _validate_operator_policy_fixture,
    _validate_kill_switch_policy_fixture,
    _validate_audit_policy_fixture,
    _universal_reject_scan,
    _correlate_evidence,
    ReadinessValidationError,
)


_AS_OF = "2026-06-24T10:00:00Z"


def _write_fixture(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _make_quality_gate(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "artifact_type": "trading_quality_gate",
        "schema_version": "trading-quality-gate.v1",
        "mode": "paper",
        "run_id": "run-123",
        "symbol": "AAPL",
        "quality_state": "eligible_for_shadow_live_quality_review",
        "blockers": [],
    }
    data.update(overrides)
    return data


def _make_shadow_comparison(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "artifact_type": "shadow_live_comparison",
        "schema_version": "shadow-live-comparison.v1",
        "run_id": "run-123",
        "symbol": "AAPL",
        "quality_state": "eligible_for_shadow_live_quality_review",
        "status": "matched",
        "freshness_assessment": {"snapshot_age_seconds": 0},
        "blockers": [],
    }
    data.update(overrides)
    return data


def _make_submit_conformance(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "artifact_type": "gated_submit_conformance",
        "schema_version": "gated-submit-conformance.v1",
        "candidate": "CAND-006",
        "mode": "simulated_only",
        "run_id": "run-123",
        "symbol": "AAPL",
        "status": "dry_run_recorded",
        "as_of": _AS_OF,
        "safety_assertions": {
            "no_live_submit": True,
            "no_broker_called": True,
            "no_provider_called": True,
            "no_credentials_loaded": True,
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
    data.update(overrides)
    return data


def _make_runtime_envelope(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
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
    }
    data.update(overrides)
    return data


def _make_broker_capabilities(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "artifact_type": "broker_capability_manifest_fixture",
        "schema_version": "broker-capability-manifest-fixture.v1",
        "broker_label": "local-test-broker",
        "capabilities": {"paper_trading": True},
        "disabled_capabilities": [],
        "unsupported_order_types": [],
        "sandbox_only": True,
        "live_api_contact_allowed": False,
        "credentials_present": False,
        "endpoint_present": False,
        "captured_at": "2026-06-24T09:00:00Z",
        "expires_at": "2026-06-24T12:00:00Z",
    }
    data.update(overrides)
    return data


def _make_operator_policy(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
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
    }
    data.update(overrides)
    return data


def _make_kill_switch_policy(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "artifact_type": "kill_switch_policy_fixture",
        "schema_version": "kill-switch-policy-fixture.v1",
        "kill_switch_required": True,
        "default_state_on_missing_runtime": "blocked",
        "default_state_on_unknown_runtime": "blocked",
        "operator_override_allowed": False,
        "expires_at": "2026-06-24T12:00:00Z",
    }
    data.update(overrides)
    return data


def _make_audit_policy(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "artifact_type": "audit_policy_fixture",
        "schema_version": "audit-policy-fixture.v1",
        "audit_required": True,
        "append_only_required": True,
        "hash_chain_required": True,
        "local_artifact_recording_required": True,
        "live_audit_chain_claimed": False,
        "expires_at": "2026-06-24T12:00:00Z",
    }
    data.update(overrides)
    return data


def _make_valid_inputs(tmp_path: Path) -> tuple[ReadinessEnvelopeInputs, dict[str, Any]]:
    fixtures: dict[str, Any] = {}
    paths: dict[str, Path] = {}

    for label, maker in (
        ("quality_gate", _make_quality_gate),
        ("shadow_comparison", _make_shadow_comparison),
        ("submit_conformance", _make_submit_conformance),
        ("runtime_envelope", _make_runtime_envelope),
        ("broker_capabilities", _make_broker_capabilities),
        ("operator_policy", _make_operator_policy),
        ("kill_switch_policy", _make_kill_switch_policy),
        ("audit_policy", _make_audit_policy),
    ):
        fixtures[label] = maker()
        paths[label] = tmp_path / f"{label}.json"
        _write_fixture(paths[label], fixtures[label])

    inputs = ReadinessEnvelopeInputs(
        quality_gate_path=paths["quality_gate"],
        shadow_comparison_path=paths["shadow_comparison"],
        submit_conformance_path=paths["submit_conformance"],
        runtime_envelope_path=paths["runtime_envelope"],
        broker_capabilities_path=paths["broker_capabilities"],
        operator_policy_path=paths["operator_policy"],
        kill_switch_policy_path=paths["kill_switch_policy"],
        audit_policy_path=paths["audit_policy"],
        output_dir=tmp_path / "out",
        as_of=_AS_OF,
    )
    return inputs, fixtures


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_approved_statuses_include_required_values() -> None:
    for status in (
        "not_evaluated",
        "blocked",
        "upstream_quality_blocked",
        "shadow_evidence_blocked",
        "submit_conformance_blocked",
        "runtime_envelope_blocked",
        "broker_capability_blocked",
        "operator_policy_blocked",
        "kill_switch_policy_blocked",
        "audit_policy_blocked",
        "envelope_synthesized",
        "readiness_envelope_recorded",
    ):
        assert status in APPROVED_FINAL_STATUSES


def test_gate_sequence_includes_required_gates() -> None:
    for gate_id in GATE_SEQUENCE:
        assert gate_id in GATE_SEQUENCE


def test_evidence_only_disclaimer_present() -> None:
    assert "simulated only" in EVIDENCE_ONLY_DISCLAIMER.lower()
    assert "not permission to submit orders" in EVIDENCE_ONLY_DISCLAIMER


# ---------------------------------------------------------------------------
# Canonicalization / fingerprinting / timestamps
# ---------------------------------------------------------------------------


def test_canonical_json_bytes_sorts_keys() -> None:
    assert canonical_json_bytes({"b": 1, "a": 2}) == b'{"a":2,"b":1}'


def test_fingerprint_format() -> None:
    fp = fingerprint_json({"a": 1})
    assert fp.startswith("sha256:")
    assert len(fp) == 7 + 64


def test_fingerprint_stable_under_key_reordering() -> None:
    a = {"b": 1, "a": 2}
    b = {"a": 2, "b": 1}
    assert fingerprint_json(a) == fingerprint_json(b)


def test_parse_as_of_utc_accepts_z() -> None:
    assert parse_as_of_utc("2026-06-24T10:00:00Z") == "2026-06-24T10:00:00Z"


def test_parse_as_of_utc_accepts_offset() -> None:
    assert parse_as_of_utc("2026-06-24T10:00:00+00:00") == "2026-06-24T10:00:00Z"


def test_parse_as_of_utc_rejects_non_utc() -> None:
    with pytest.raises(Exception):
        parse_as_of_utc("2026-06-24T10:00:00+01:00")


def test_parse_as_of_utc_rejects_naive() -> None:
    with pytest.raises(Exception):
        parse_as_of_utc("2026-06-24T10:00:00")


# ---------------------------------------------------------------------------
# Projection validators
# ---------------------------------------------------------------------------


def test_validate_quality_gate_projection_pass() -> None:
    data = _make_quality_gate(extra_field="ignored")
    result = _validate_quality_gate(data)
    assert result["artifact_type"] == "trading_quality_gate"
    assert result["mode"] == "paper"
    assert "extra_field" not in result


def test_validate_quality_gate_rejects_bad_schema_version() -> None:
    with pytest.raises(ReadinessValidationError):
        _validate_quality_gate(_make_quality_gate(schema_version="v99"))


def test_validate_quality_gate_rejects_non_list_blockers() -> None:
    with pytest.raises(ReadinessValidationError):
        _validate_quality_gate(_make_quality_gate(blockers="none"))


def test_validate_shadow_comparison_projection_pass() -> None:
    data = _make_shadow_comparison(extra="ignored")
    result = _validate_shadow_comparison(data)
    assert result["status"] == "matched"
    assert "extra" not in result


def test_validate_shadow_comparison_rejects_non_dict_freshness() -> None:
    with pytest.raises(ReadinessValidationError):
        _validate_shadow_comparison(_make_shadow_comparison(freshness_assessment="old"))


def test_validate_submit_conformance_projection_pass() -> None:
    result = _validate_submit_conformance(_make_submit_conformance(), _AS_OF)
    assert result["candidate"] == "CAND-006"
    assert result["status"] == "dry_run_recorded"


def test_validate_submit_conformance_rejects_non_dict_safety_assertions() -> None:
    with pytest.raises(ReadinessValidationError):
        _validate_submit_conformance(
            _make_submit_conformance(safety_assertions="safe"), _AS_OF
        )


def test_submit_conformance_future_as_of_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["submit_conformance"]["as_of"] = "2026-06-25T10:00:00Z"
    _write_fixture(inputs.submit_conformance_path, fixtures["submit_conformance"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "submit_conformance_blocked"
    assert report.exit_code == 2


# ---------------------------------------------------------------------------
# Closed-schema fixture validators
# ---------------------------------------------------------------------------


def test_validate_runtime_envelope_fixture_pass() -> None:
    result = _validate_runtime_envelope_fixture(_make_runtime_envelope(), _AS_OF)
    assert result["live_submit_enabled"] is False
    assert result["max_daily_orders"] == 10


def test_validate_runtime_envelope_fixture_rejects_unknown_key() -> None:
    with pytest.raises(ReadinessValidationError):
        _validate_runtime_envelope_fixture(
            _make_runtime_envelope(unknown_field="x"), _AS_OF
        )


def test_validate_runtime_envelope_fixture_rejects_non_integer_max_daily_orders() -> None:
    with pytest.raises(ReadinessValidationError):
        _validate_runtime_envelope_fixture(
            _make_runtime_envelope(max_daily_orders="ten"), _AS_OF
        )


def test_validate_broker_capability_manifest_pass() -> None:
    result = _validate_broker_capability_manifest(_make_broker_capabilities(), _AS_OF)
    assert result["sandbox_only"] is True
    assert result["credentials_present"] is False


def test_validate_broker_capability_manifest_rejects_non_bool_flag() -> None:
    with pytest.raises(ReadinessValidationError):
        _validate_broker_capability_manifest(
            _make_broker_capabilities(credentials_present="false"), _AS_OF
        )


def test_validate_operator_policy_fixture_pass() -> None:
    result = _validate_operator_policy_fixture(_make_operator_policy(), _AS_OF, "AAPL")
    assert result["approval_scope"] == "simulated_only"


def test_validate_operator_policy_fixture_rejects_non_bool_flag() -> None:
    with pytest.raises(ReadinessValidationError):
        _validate_operator_policy_fixture(
            _make_operator_policy(requires_manual_review="yes"), _AS_OF, "AAPL"
        )


def test_validate_kill_switch_policy_fixture_pass() -> None:
    result = _validate_kill_switch_policy_fixture(_make_kill_switch_policy(), _AS_OF)
    assert result["operator_override_allowed"] is False


def test_validate_kill_switch_policy_fixture_rejects_non_string_default_state() -> None:
    with pytest.raises(ReadinessValidationError):
        _validate_kill_switch_policy_fixture(
            _make_kill_switch_policy(default_state_on_unknown_runtime=123), _AS_OF
        )


def test_validate_audit_policy_fixture_pass() -> None:
    result = _validate_audit_policy_fixture(_make_audit_policy(), _AS_OF)
    assert result["live_audit_chain_claimed"] is False


def test_validate_audit_policy_fixture_rejects_non_bool_flag() -> None:
    with pytest.raises(ReadinessValidationError):
        _validate_audit_policy_fixture(
            _make_audit_policy(audit_required="yes"), _AS_OF
        )


# ---------------------------------------------------------------------------
# Universal rejection scanner
# ---------------------------------------------------------------------------


def test_universal_reject_scan_finds_secret_key() -> None:
    findings = _universal_reject_scan({"api_key": "x"})
    assert any("secret-like key" in f for f in findings)


def test_universal_reject_scan_finds_endpoint_key() -> None:
    findings = _universal_reject_scan({"endpoint": "x"})
    assert any("endpoint-like key" in f for f in findings)


def test_universal_reject_scan_finds_forbidden_key() -> None:
    findings = _universal_reject_scan({"client_order_id": "x"})
    assert any("forbidden key" in f for f in findings)


def test_universal_reject_scan_finds_url_value() -> None:
    findings = _universal_reject_scan({"note": "contact https://example.com"})
    assert any("url protocol value" in f for f in findings)


def test_universal_reject_scan_finds_secret_value() -> None:
    findings = _universal_reject_scan({"note": "token is ghp_abc123"})
    assert any("secret-like value" in f for f in findings)


# ---------------------------------------------------------------------------
# Evidence correlation
# ---------------------------------------------------------------------------


def _sample_normalized() -> dict[str, Any]:
    return {
        "quality_gate": {"run_id": "run-123", "symbol": "AAPL", "blockers": []},
        "shadow_comparison": {"run_id": "run-123", "symbol": "AAPL", "blockers": []},
        "submit_conformance": {
            "run_id": "run-123",
            "symbol": "AAPL",
            "candidate": "CAND-006",
            "blockers": [],
        },
        "runtime_envelope": {"run_id": "run-123", "symbol": "AAPL"},
        "operator_policy": {"allowed_symbols": ["AAPL"], "blocked_symbols": []},
    }


def test_correlate_evidence_empty_on_valid() -> None:
    assert _correlate_evidence(_sample_normalized()) == []


def test_correlate_evidence_finds_run_id_mismatch() -> None:
    normalized = _sample_normalized()
    normalized["shadow_comparison"]["run_id"] = "run-other"
    blockers = _correlate_evidence(normalized)
    assert any("run_id mismatch" in b for b in blockers)


def test_correlate_evidence_finds_symbol_mismatch() -> None:
    normalized = _sample_normalized()
    normalized["submit_conformance"]["symbol"] = "TSLA"
    blockers = _correlate_evidence(normalized)
    assert any("symbol mismatch" in b for b in blockers)


# ---------------------------------------------------------------------------
# Gate engine
# ---------------------------------------------------------------------------


def test_valid_all_pass_envelope(tmp_path: Path) -> None:
    inputs, _ = _make_valid_inputs(tmp_path)
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "envelope_synthesized"
    assert report.exit_code == 2
    gate_statuses = {g.gate_id: g.status for g in report.gates}
    assert gate_statuses["schema_preflight"] == "pass"
    assert gate_statuses["cand004_evidence_gate"] == "pass"
    assert gate_statuses["cand005_evidence_gate"] == "pass"
    assert gate_statuses["cand006_evidence_gate"] == "pass"
    assert gate_statuses["envelope_synthesis_gate"] == "pass"
    assert gate_statuses["artifact_recording_gate"] == "not_run"


def test_run_id_mismatch_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["quality_gate"]["run_id"] = "run-other"
    _write_fixture(inputs.quality_gate_path, fixtures["quality_gate"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "upstream_quality_blocked"
    assert report.exit_code == 2
    assert report.gates[1].gate_id == "cand004_evidence_gate"
    assert report.gates[1].status == "fail"
    assert all(g.status == "not_run" for g in report.gates[2:])


def test_symbol_mismatch_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["shadow_comparison"]["symbol"] = "TSLA"
    _write_fixture(inputs.shadow_comparison_path, fixtures["shadow_comparison"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "upstream_quality_blocked"
    assert report.exit_code == 2


def test_blocked_quality_gate_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["quality_gate"]["blockers"] = ["quality_signal_missing"]
    _write_fixture(inputs.quality_gate_path, fixtures["quality_gate"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "upstream_quality_blocked"
    assert report.exit_code == 2


def test_quality_gate_wrong_mode_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["quality_gate"]["mode"] = "live"
    _write_fixture(inputs.quality_gate_path, fixtures["quality_gate"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "upstream_quality_blocked"
    assert report.exit_code == 2


def test_shadow_comparison_not_matched_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["shadow_comparison"]["status"] = "minor_divergence"
    _write_fixture(inputs.shadow_comparison_path, fixtures["shadow_comparison"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "shadow_evidence_blocked"
    assert report.exit_code == 2
    assert all(
        g.status == "not_run"
        for g in report.gates
        if g.gate_id in GATE_SEQUENCE[GATE_SEQUENCE.index("cand006_evidence_gate") :]
    )


def test_submit_conformance_not_recorded_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["submit_conformance"]["status"] = "dry_run_ready"
    _write_fixture(inputs.submit_conformance_path, fixtures["submit_conformance"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "submit_conformance_blocked"
    assert report.exit_code == 2


def test_submit_conformance_transmission_enabled_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["submit_conformance"]["dry_run_request"]["transmission"]["allowed"] = True
    _write_fixture(inputs.submit_conformance_path, fixtures["submit_conformance"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "submit_conformance_blocked"
    assert report.exit_code == 2


def test_submit_conformance_stale_evidence_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["submit_conformance"]["as_of"] = "2026-06-23T09:00:00Z"
    _write_fixture(inputs.submit_conformance_path, fixtures["submit_conformance"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "submit_conformance_blocked"
    assert report.exit_code == 2
    assert any(
        g.gate_id == "cand006_evidence_gate" and g.status == "fail" and "older than 24 hours" in g.reason
        for g in report.gates
    )


def test_missing_quality_gate_blocks(tmp_path: Path) -> None:
    inputs, _ = _make_valid_inputs(tmp_path)
    inputs.quality_gate_path.rename(inputs.quality_gate_path.with_suffix(".missing"))
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "not_evaluated"
    assert report.exit_code == 2
    assert report.gates[0].status == "fail"


def test_missing_shadow_comparison_blocks(tmp_path: Path) -> None:
    inputs, _ = _make_valid_inputs(tmp_path)
    inputs.shadow_comparison_path.rename(
        inputs.shadow_comparison_path.with_suffix(".missing")
    )
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "not_evaluated"
    assert report.exit_code == 2
    assert report.gates[0].status == "fail"


def test_missing_submit_conformance_blocks(tmp_path: Path) -> None:
    inputs, _ = _make_valid_inputs(tmp_path)
    inputs.submit_conformance_path.rename(
        inputs.submit_conformance_path.with_suffix(".missing")
    )
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "not_evaluated"
    assert report.exit_code == 2
    assert report.gates[0].status == "fail"


def test_runtime_envelope_live_submit_enabled_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["runtime_envelope"]["live_submit_enabled"] = True
    _write_fixture(inputs.runtime_envelope_path, fixtures["runtime_envelope"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "runtime_envelope_blocked"
    assert report.exit_code == 2


def test_runtime_envelope_empty_supported_order_types_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["runtime_envelope"]["supported_order_types"] = []
    _write_fixture(inputs.runtime_envelope_path, fixtures["runtime_envelope"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "runtime_envelope_blocked"
    assert report.exit_code == 2


def test_runtime_envelope_empty_supported_time_in_force_blocks(
    tmp_path: Path,
) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["runtime_envelope"]["supported_time_in_force"] = []
    _write_fixture(inputs.runtime_envelope_path, fixtures["runtime_envelope"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "runtime_envelope_blocked"
    assert report.exit_code == 2


def test_broker_capability_credentials_present_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["broker_capabilities"]["credentials_present"] = True
    _write_fixture(inputs.broker_capabilities_path, fixtures["broker_capabilities"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "broker_capability_blocked"
    assert report.exit_code == 2


def test_broker_capability_endpoint_present_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["broker_capabilities"]["endpoint_present"] = True
    _write_fixture(inputs.broker_capabilities_path, fixtures["broker_capabilities"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "broker_capability_blocked"
    assert report.exit_code == 2


def test_broker_label_prefix_enforced(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["broker_capabilities"]["broker_label"] = "live-broker"
    _write_fixture(inputs.broker_capabilities_path, fixtures["broker_capabilities"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "broker_capability_blocked"
    assert report.exit_code == 2


def test_operator_policy_unattended_allowed_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["operator_policy"]["unattended_operation_allowed"] = True
    _write_fixture(inputs.operator_policy_path, fixtures["operator_policy"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "operator_policy_blocked"
    assert report.exit_code == 2


def test_operator_policy_symbol_blocked_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["operator_policy"]["blocked_symbols"] = ["AAPL"]
    _write_fixture(inputs.operator_policy_path, fixtures["operator_policy"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "operator_policy_blocked"
    assert report.exit_code == 2


@pytest.mark.parametrize(
    "mutation",
    [
        {"allowed_symbols": ["TSLA"], "blocked_symbols": []},
        {"allowed_symbols": [], "blocked_symbols": ["AAPL"]},
    ],
)
def test_operator_policy_symbol_allow_and_block(
    tmp_path: Path, mutation: dict[str, Any]
) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["operator_policy"].update(mutation)
    _write_fixture(inputs.operator_policy_path, fixtures["operator_policy"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "operator_policy_blocked"
    assert report.exit_code == 2


def test_kill_switch_policy_default_unknown_not_blocked_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["kill_switch_policy"]["default_state_on_unknown_runtime"] = "allowed"
    _write_fixture(inputs.kill_switch_policy_path, fixtures["kill_switch_policy"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "kill_switch_policy_blocked"
    assert report.exit_code == 2


def test_audit_policy_hash_chain_not_required_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["audit_policy"]["hash_chain_required"] = False
    _write_fixture(inputs.audit_policy_path, fixtures["audit_policy"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "audit_policy_blocked"
    assert report.exit_code == 2


def test_fixture_expiry_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["runtime_envelope"]["expires_at"] = "2026-06-24T09:00:00Z"
    _write_fixture(inputs.runtime_envelope_path, fixtures["runtime_envelope"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.exit_code == 2
    assert report.status == "not_evaluated"
    assert report.gates[0].status == "fail"


def test_unknown_fixture_fields_rejected(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["audit_policy"]["extra_field"] = "unexpected"
    _write_fixture(inputs.audit_policy_path, fixtures["audit_policy"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "not_evaluated"
    assert report.exit_code == 2


def test_secret_like_fields_rejected(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["broker_capabilities"]["api_key"] = "secret"
    _write_fixture(inputs.broker_capabilities_path, fixtures["broker_capabilities"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "not_evaluated"
    assert report.exit_code == 2


def test_url_protocol_fields_rejected(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["operator_policy"]["note"] = "see https://example.com"
    _write_fixture(inputs.operator_policy_path, fixtures["operator_policy"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "not_evaluated"
    assert report.exit_code == 2


# ---------------------------------------------------------------------------
# Report contents
# ---------------------------------------------------------------------------


def test_report_contains_required_fields(tmp_path: Path) -> None:
    inputs, _ = _make_valid_inputs(tmp_path)
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.artifact_type == "runtime_readiness_envelope"
    assert report.candidate == "CAND-007"
    assert report.mode == "simulated_only"
    assert report.disclaimer == EVIDENCE_ONLY_DISCLAIMER
    assert report.input_digest.startswith("sha256:")
    assert report.envelope_digest.startswith("sha256:")
    assert report.evaluation_id.startswith("re-")
    assert set(report.input_artifacts) == set(
        [
            "quality_gate",
            "shadow_comparison",
            "submit_conformance",
            "runtime_envelope",
            "broker_capabilities",
            "operator_policy",
            "kill_switch_policy",
            "audit_policy",
        ]
    )


def test_report_to_dict_is_json_serializable(tmp_path: Path) -> None:
    inputs, _ = _make_valid_inputs(tmp_path)
    report = build_runtime_readiness_envelope_report(inputs)
    text = json.dumps(report.to_dict(), sort_keys=True, ensure_ascii=True)
    assert "envelope_synthesized" in text
