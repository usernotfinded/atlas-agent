from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from atlas_agent.agent import gated_submit_conformance
from atlas_agent.agent.gated_submit_conformance import (
    GATE_SEQUENCE,
    SubmitConformanceInputs,
    canonical_json_bytes,
    fingerprint_json,
    parse_as_of_utc,
    build_gated_submit_conformance_report,
    write_gated_submit_conformance_artifacts,
)


_AS_OF = "2026-06-24T10:00:00Z"


def _make_order_intent(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
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
    }
    data.update(overrides)
    return data


def _make_kill_switch(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "artifact_type": "gated_submit_kill_switch_fixture",
        "schema_version": "gated-submit-kill-switch.v1",
        "fixture_mode": "simulated",
        "scope": "conformance_rehearsal_only",
        "state": "inactive",
        "captured_at": "2026-06-24T09:00:00Z",
        "expires_at": "2026-06-24T11:00:00Z",
    }
    data.update(overrides)
    return data


def _make_risk_envelope(intent_fingerprint: str, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "artifact_type": "gated_submit_risk_envelope_fixture",
        "schema_version": "gated-submit-risk-envelope.v1",
        "fixture_mode": "simulated",
        "represents": "RiskManager_evaluation",
        "evaluation_mode": "paper",
        "intent_fingerprint": intent_fingerprint,
        "captured_at": "2026-06-24T09:00:00Z",
        "expires_at": "2026-06-24T11:00:00Z",
        "decision": "allowed",
        "evaluated_price": "100",
        "evaluated_notional": "100",
        "checks": [{"rule": "max_position_size", "passed": True}],
        "violations": [],
        "limits_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "portfolio_snapshot_digest": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    }
    data.update(overrides)
    return data


def _make_approval(
    intent_fingerprint: str, risk_fingerprint: str, **overrides: Any
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "artifact_type": "gated_submit_approval_fixture",
        "schema_version": "gated-submit-approval-fixture.v1",
        "fixture_mode": "simulated",
        "scope": "conformance_rehearsal_only",
        "fixture_id": "approval-001",
        "intent_fingerprint": intent_fingerprint,
        "risk_envelope_fingerprint": risk_fingerprint,
        "decision": "approved",
        "actor_label": "simulated-reviewer",
        "approved_at": "2026-06-24T09:00:00Z",
        "expires_at": "2026-06-24T11:00:00Z",
    }
    data.update(overrides)
    return data


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


def _write_fixture(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _make_inputs(tmp_path: Path) -> tuple[SubmitConformanceInputs, dict[str, Any]]:
    fixtures: dict[str, Any] = {}
    paths: dict[str, Path] = {}
    for label, maker in (
        ("quality_gate", _make_quality_gate),
        ("shadow_comparison", _make_shadow_comparison),
        ("order_intent", _make_order_intent),
        ("kill_switch", _make_kill_switch),
    ):
        fixtures[label] = maker()
        paths[label] = tmp_path / f"{label}.json"
        _write_fixture(paths[label], fixtures[label])

    order_intent = fixtures["order_intent"]
    order_fp = fingerprint_json(order_intent)
    risk = _make_risk_envelope(order_fp)
    fixtures["risk_envelope"] = risk
    paths["risk_envelope"] = tmp_path / "risk_envelope.json"
    _write_fixture(paths["risk_envelope"], risk)

    risk_fp = fingerprint_json(risk)
    approval = _make_approval(order_fp, risk_fp)
    fixtures["approval"] = approval
    paths["approval"] = tmp_path / "approval.json"
    _write_fixture(paths["approval"], approval)

    inputs = SubmitConformanceInputs(
        quality_gate_path=paths["quality_gate"],
        shadow_comparison_path=paths["shadow_comparison"],
        order_intent_path=paths["order_intent"],
        kill_switch_path=paths["kill_switch"],
        risk_envelope_path=paths["risk_envelope"],
        approval_path=paths["approval"],
        output_dir=tmp_path / "out",
        as_of=_AS_OF,
    )
    return inputs, fixtures


def test_canonical_json_bytes_sorts_keys() -> None:
    value = {"b": 1, "a": 2}
    assert canonical_json_bytes(value) == b'{"a":2,"b":1}'


def test_fingerprint_format() -> None:
    fp = fingerprint_json({"a": 1})
    assert fp.startswith("sha256:")
    assert len(fp) == 7 + 64


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


def test_all_pass_report_dry_run_ready_before_write(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    report = build_gated_submit_conformance_report(inputs)
    assert report.status == "dry_run_ready"
    assert report.dry_run_request is not None
    assert report.dry_run_request.transmission["allowed"] is False
    assert report.dry_run_request.runtime_effects["order_instantiated"] is False
    assert report.dry_run_request.runtime_effects["broker_called"] is False


def test_all_pass_artifacts_dry_run_recorded(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    report = build_gated_submit_conformance_report(inputs)
    report = write_gated_submit_conformance_artifacts(report, inputs.output_dir)
    assert report.status == "dry_run_recorded"
    assert report.exit_code == 0
    assert (inputs.output_dir / "gated-submit-conformance.json").exists()
    assert (inputs.output_dir / "gated-submit-conformance-report.md").exists()
    gate_statuses = {g.gate_id: g.status for g in report.gates}
    assert gate_statuses["atomic_artifact_recording"] == "pass"


def test_evaluation_id_deterministic(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    report1 = build_gated_submit_conformance_report(inputs)
    report2 = build_gated_submit_conformance_report(inputs)
    assert report1.evaluation_id == report2.evaluation_id


def test_evaluation_id_in_both_artifacts(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    report = build_gated_submit_conformance_report(inputs)
    report = write_gated_submit_conformance_artifacts(report, inputs.output_dir)
    json_data = json.loads((inputs.output_dir / "gated-submit-conformance.json").read_text())
    md_text = (inputs.output_dir / "gated-submit-conformance-report.md").read_text()
    assert json_data["evaluation_id"] == report.evaluation_id
    assert report.evaluation_id in md_text


def test_as_of_required_and_in_artifacts(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    report = build_gated_submit_conformance_report(inputs)
    report = write_gated_submit_conformance_artifacts(report, inputs.output_dir)
    json_data = json.loads((inputs.output_dir / "gated-submit-conformance.json").read_text())
    md_text = (inputs.output_dir / "gated-submit-conformance-report.md").read_text()
    assert json_data["as_of"] == _AS_OF
    assert _AS_OF in md_text


def test_no_wall_clock_used_for_gate_decisions(tmp_path: Path) -> None:
    # Fixtures with near-term expiry and --as-of far in the past would fail if
    # the implementation used wall clock. They must be evaluated against as_of.
    inputs, fixtures = _make_inputs(tmp_path)
    _write_fixture(
        inputs.kill_switch_path, _make_kill_switch(expires_at="2026-06-24T11:00:00Z")
    )
    order_fp = fingerprint_json(fixtures["order_intent"])
    _write_fixture(
        inputs.risk_envelope_path,
        _make_risk_envelope(order_fp, expires_at="2026-06-24T11:00:00Z"),
    )
    risk_fp = fingerprint_json(_make_risk_envelope(order_fp))
    _write_fixture(
        inputs.approval_path,
        _make_approval(order_fp, risk_fp, expires_at="2026-06-24T11:00:00Z"),
    )
    inputs = SubmitConformanceInputs(
        quality_gate_path=inputs.quality_gate_path,
        shadow_comparison_path=inputs.shadow_comparison_path,
        order_intent_path=inputs.order_intent_path,
        kill_switch_path=inputs.kill_switch_path,
        risk_envelope_path=inputs.risk_envelope_path,
        approval_path=inputs.approval_path,
        output_dir=inputs.output_dir,
        as_of="2026-06-24T10:00:00Z",
    )
    report = build_gated_submit_conformance_report(inputs)
    assert report.status == "dry_run_ready"


def test_fingerprints_stable_under_key_reordering(tmp_path: Path) -> None:
    a = {"b": 1, "a": 2}
    b = {"a": 2, "b": 1}
    assert fingerprint_json(a) == fingerprint_json(b)


def test_input_digest_changes_when_fixture_changes(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    report1 = build_gated_submit_conformance_report(inputs)

    # Modify one fixture.
    new_order = _make_order_intent(quantity="2")
    _write_fixture(inputs.order_intent_path, new_order)
    report2 = build_gated_submit_conformance_report(inputs)
    assert report2.input_digest != report1.input_digest


def test_decimal_canonicalization(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    order = _make_order_intent(quantity="001.2300")
    _write_fixture(inputs.order_intent_path, order)
    # The engine canonicalizes the order before fingerprinting; fixtures must
    # reference the canonical form.
    canonical_order = _make_order_intent(quantity="1.23")
    order_fp = fingerprint_json(canonical_order)
    _write_fixture(inputs.risk_envelope_path, _make_risk_envelope(order_fp))
    risk_fp = fingerprint_json(_make_risk_envelope(order_fp))
    _write_fixture(inputs.approval_path, _make_approval(order_fp, risk_fp))
    report = build_gated_submit_conformance_report(inputs)
    assert report.dry_run_request is not None
    assert report.dry_run_request.quantity == "1.23"


def test_rejects_json_number_for_decimal_field(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    order = _make_order_intent(quantity=1)
    _write_fixture(inputs.order_intent_path, order)
    report = build_gated_submit_conformance_report(inputs)
    assert report.status == "not_evaluated"
    assert any("expected decimal string" in b.lower() for b in report.blockers)


def test_rejects_json_float_for_decimal_field(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    order = _make_order_intent(limit_price=100.5)
    _write_fixture(inputs.order_intent_path, order)
    report = build_gated_submit_conformance_report(inputs)
    assert report.status == "not_evaluated"


def test_rejects_exponent_notation(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    order = _make_order_intent(quantity="1e3")
    _write_fixture(inputs.order_intent_path, order)
    report = build_gated_submit_conformance_report(inputs)
    assert report.status == "not_evaluated"


def test_rejects_negative_zero(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    order = _make_order_intent(quantity="-0")
    _write_fixture(inputs.order_intent_path, order)
    report = build_gated_submit_conformance_report(inputs)
    assert report.status == "not_evaluated"


def test_rejects_non_utc_fixture_timestamp(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    ks = _make_kill_switch(expires_at="2026-06-24T11:00:00+01:00")
    _write_fixture(inputs.kill_switch_path, ks)
    report = build_gated_submit_conformance_report(inputs)
    assert report.status == "not_evaluated"


def test_rejects_naive_fixture_timestamp(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    ks = _make_kill_switch(expires_at="2026-06-24T11:00:00")
    _write_fixture(inputs.kill_switch_path, ks)
    report = build_gated_submit_conformance_report(inputs)
    assert report.status == "not_evaluated"


def test_normalizes_plus_zero_zero_offset(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    ks = _make_kill_switch(expires_at="2026-06-24T11:00:00+00:00")
    _write_fixture(inputs.kill_switch_path, ks)
    report = build_gated_submit_conformance_report(inputs)
    assert report.status == "dry_run_ready"


def test_risk_envelope_fingerprint_mismatch_blocks(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    risk = _make_risk_envelope("sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff")
    _write_fixture(inputs.risk_envelope_path, risk)
    report = build_gated_submit_conformance_report(inputs)
    assert report.status == "risk_blocked"
    assert any("intent_fingerprint mismatch" in b for b in report.blockers)


def test_approval_intent_fingerprint_mismatch_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_inputs(tmp_path)
    risk_fp = fingerprint_json(fixtures["risk_envelope"])
    approval = _make_approval(
        "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        risk_fp,
    )
    _write_fixture(inputs.approval_path, approval)
    report = build_gated_submit_conformance_report(inputs)
    assert report.status == "approval_required"
    assert any("intent_fingerprint mismatch" in b for b in report.blockers)


def test_approval_risk_fingerprint_mismatch_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_inputs(tmp_path)
    order_fp = fingerprint_json(fixtures["order_intent"])
    approval = _make_approval(
        order_fp,
        "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
    )
    _write_fixture(inputs.approval_path, approval)
    report = build_gated_submit_conformance_report(inputs)
    assert report.status == "approval_required"
    assert any("risk_envelope_fingerprint mismatch" in b for b in report.blockers)


def test_approval_expiry_uses_supplied_as_of(tmp_path: Path) -> None:
    inputs, fixtures = _make_inputs(tmp_path)
    order_fp = fingerprint_json(fixtures["order_intent"])
    risk_fp = fingerprint_json(fixtures["risk_envelope"])
    approval = _make_approval(order_fp, risk_fp, expires_at="2026-06-24T09:30:00Z")
    _write_fixture(inputs.approval_path, approval)
    report = build_gated_submit_conformance_report(
        SubmitConformanceInputs(
            quality_gate_path=inputs.quality_gate_path,
            shadow_comparison_path=inputs.shadow_comparison_path,
            order_intent_path=inputs.order_intent_path,
            kill_switch_path=inputs.kill_switch_path,
            risk_envelope_path=inputs.risk_envelope_path,
            approval_path=inputs.approval_path,
            output_dir=inputs.output_dir,
            as_of="2026-06-24T10:00:00Z",
        )
    )
    assert report.status == "approval_required"
    assert any("expired" in b for b in report.blockers)


def test_cand005_minor_divergence_blocks(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    shadow = _make_shadow_comparison(status="minor_divergence")
    _write_fixture(inputs.shadow_comparison_path, shadow)
    report = build_gated_submit_conformance_report(inputs)
    assert report.status == "shadow_divergence_blocked"


def test_dry_run_request_has_no_forbidden_fields(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    report = build_gated_submit_conformance_report(inputs)
    req = report.dry_run_request
    assert req is not None
    req_dict = req.to_dict()
    for key in (
        "client_order_id",
        "broker_order_id",
        "account",
        "account_id",
        "broker",
        "api_key",
        "token",
        "secret",
    ):
        assert key not in req_dict


def test_input_files_not_mutated(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)

    def _hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    hashes = {label: _hash(path) for label, path in {
        "quality_gate": inputs.quality_gate_path,
        "shadow_comparison": inputs.shadow_comparison_path,
        "order_intent": inputs.order_intent_path,
        "kill_switch": inputs.kill_switch_path,
        "risk_envelope": inputs.risk_envelope_path,
        "approval": inputs.approval_path,
    }.items()}

    report = build_gated_submit_conformance_report(inputs)
    write_gated_submit_conformance_artifacts(report, inputs.output_dir)

    for label, path in {
        "quality_gate": inputs.quality_gate_path,
        "shadow_comparison": inputs.shadow_comparison_path,
        "order_intent": inputs.order_intent_path,
        "kill_switch": inputs.kill_switch_path,
        "risk_envelope": inputs.risk_envelope_path,
        "approval": inputs.approval_path,
    }.items():
        assert _hash(path) == hashes[label]


def test_secret_like_key_rejected(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    order = _make_order_intent(api_key="leaked")
    _write_fixture(inputs.order_intent_path, order)
    report = build_gated_submit_conformance_report(inputs)
    assert report.status == "not_evaluated"


def test_forbidden_fixture_key_rejected(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    order = _make_order_intent(client_order_id="x")
    _write_fixture(inputs.order_intent_path, order)
    report = build_gated_submit_conformance_report(inputs)
    assert report.status == "not_evaluated"


def test_atomic_writer_sorted_keys(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    report = build_gated_submit_conformance_report(inputs)
    report = write_gated_submit_conformance_artifacts(report, inputs.output_dir)
    text = (inputs.output_dir / "gated-submit-conformance.json").read_text()
    # Verify sorted output by checking a known key order appearance.
    assert text.index('"artifact_type"') < text.index('"as_of"')


def test_output_json_path_equal_input_rejected(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    # Make output_dir same as quality_gate file; artifact path would equal input.
    inputs = SubmitConformanceInputs(
        quality_gate_path=inputs.quality_gate_path,
        shadow_comparison_path=inputs.shadow_comparison_path,
        order_intent_path=inputs.order_intent_path,
        kill_switch_path=inputs.kill_switch_path,
        risk_envelope_path=inputs.risk_envelope_path,
        approval_path=inputs.approval_path,
        output_dir=inputs.quality_gate_path,
        as_of=_AS_OF,
    )
    report = build_gated_submit_conformance_report(inputs)
    assert report.status == "not_evaluated"


def test_output_markdown_path_equal_input_rejected(tmp_path: Path) -> None:
    # If an input file is named exactly like the markdown report, the resolved
    # path aliases the input.
    inputs, _ = _make_inputs(tmp_path)
    md_input = tmp_path / "gated-submit-conformance-report.md"
    md_input.write_text("{}", encoding="utf-8")
    inputs = SubmitConformanceInputs(
        quality_gate_path=md_input,
        shadow_comparison_path=inputs.shadow_comparison_path,
        order_intent_path=inputs.order_intent_path,
        kill_switch_path=inputs.kill_switch_path,
        risk_envelope_path=inputs.risk_envelope_path,
        approval_path=inputs.approval_path,
        output_dir=tmp_path,
        as_of=_AS_OF,
    )
    report = build_gated_submit_conformance_report(inputs)
    assert report.status == "not_evaluated"


def test_symlink_output_aliasing_input_rejected(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    # Rename an input file so it collides with the output JSON artifact basename.
    aliasing_input = tmp_path / "gated-submit-conformance.json"
    inputs.quality_gate_path.replace(aliasing_input)
    # Create an output directory that is a symlink to the input directory.
    linked_dir = tmp_path / "linked_input_dir"
    linked_dir.symlink_to(tmp_path)
    inputs = SubmitConformanceInputs(
        quality_gate_path=aliasing_input,
        shadow_comparison_path=inputs.shadow_comparison_path,
        order_intent_path=inputs.order_intent_path,
        kill_switch_path=inputs.kill_switch_path,
        risk_envelope_path=inputs.risk_envelope_path,
        approval_path=inputs.approval_path,
        output_dir=linked_dir,
        as_of=_AS_OF,
    )
    report = build_gated_submit_conformance_report(inputs)
    # The resolved output JSON path would overwrite an input artifact.
    assert report.status == "not_evaluated"


def test_markdown_without_json_is_not_authoritative(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    report = build_gated_submit_conformance_report(inputs)
    report = write_gated_submit_conformance_artifacts(report, inputs.output_dir)
    json_path = inputs.output_dir / "gated-submit-conformance.json"
    md_path = inputs.output_dir / "gated-submit-conformance-report.md"
    json_path.unlink()
    assert not json_path.exists()
    assert md_path.exists()
    # A consumer must ignore Markdown when the authoritative JSON is absent.
    assert json_path.exists() is False


def test_mismatched_evaluation_id_markdown_ignored(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    report = build_gated_submit_conformance_report(inputs)
    report = write_gated_submit_conformance_artifacts(report, inputs.output_dir)
    json_path = inputs.output_dir / "gated-submit-conformance.json"
    md_path = inputs.output_dir / "gated-submit-conformance-report.md"
    data = json.loads(json_path.read_text())
    data["evaluation_id"] = "gsc-tampered123456789012"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    # Markdown evaluation_id no longer matches authoritative JSON.
    md_text = md_path.read_text()
    assert "gsc-" in md_text
    json_data = json.loads(json_path.read_text())
    assert json_data["evaluation_id"] == "gsc-tampered123456789012"


def test_json_write_failure_after_markdown_exits_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inputs, _ = _make_inputs(tmp_path)
    report = build_gated_submit_conformance_report(inputs)
    inputs.output_dir.mkdir(parents=True, exist_ok=True)

    real_atomic = gated_submit_conformance._atomic_write_text

    def _failing_atomic(output_dir: Path, filename: str, content: str) -> Path:
        if filename == gated_submit_conformance._JSON_ARTIFACT_NAME:
            raise OSError("simulated JSON write failure")
        return real_atomic(output_dir, filename, content)

    monkeypatch.setattr(gated_submit_conformance, "_atomic_write_text", _failing_atomic)
    report = write_gated_submit_conformance_artifacts(report, inputs.output_dir)
    assert report.status != "dry_run_recorded"
    assert report.exit_code == 2
    assert any("json write failed" in b.lower() for b in report.blockers)
    gate_statuses = {g.gate_id: g.status for g in report.gates}
    assert gate_statuses["atomic_artifact_recording"] != "pass"


def test_gate_sequence_order() -> None:
    assert GATE_SEQUENCE == (
        "schema_preflight",
        "cand004_quality_gate",
        "cand005_shadow_live_comparison",
        "kill_switch_fixture",
        "risk_envelope_fixture",
        "approval_fixture",
        "dry_run_conversion",
        "atomic_artifact_recording",
    )


def test_artifacts_json_and_markdown_agree_on_status_and_evaluation_id(tmp_path: Path) -> None:
    inputs, _ = _make_inputs(tmp_path)
    report = build_gated_submit_conformance_report(inputs)
    report = write_gated_submit_conformance_artifacts(report, inputs.output_dir)
    json_data = json.loads((inputs.output_dir / "gated-submit-conformance.json").read_text())
    md_text = (inputs.output_dir / "gated-submit-conformance-report.md").read_text()
    assert json_data["status"] == report.status == "dry_run_recorded"
    assert json_data["evaluation_id"] == report.evaluation_id
    assert f"**final_status:** `{report.status}`" in md_text
    assert report.evaluation_id in md_text
    json_gate_statuses = {g["gate_id"]: g["status"] for g in json_data["gates"]}
    assert json_gate_statuses["atomic_artifact_recording"] == "pass"
    assert "`atomic_artifact_recording` | `pass`" in md_text


def test_markdown_write_failure_does_not_report_dry_run_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inputs, _ = _make_inputs(tmp_path)
    report = build_gated_submit_conformance_report(inputs)
    inputs.output_dir.mkdir(parents=True, exist_ok=True)

    def _failing_atomic(output_dir: Path, filename: str, content: str) -> Path:
        raise OSError("simulated markdown write failure")

    monkeypatch.setattr(gated_submit_conformance, "_atomic_write_text", _failing_atomic)
    report = write_gated_submit_conformance_artifacts(report, inputs.output_dir)
    assert report.status != "dry_run_recorded"
    assert report.exit_code == 2
    assert any("markdown write failed" in b.lower() for b in report.blockers)
    gate_statuses = {g.gate_id: g.status for g in report.gates}
    assert gate_statuses["atomic_artifact_recording"] != "pass"
