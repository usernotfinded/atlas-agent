"""End-to-end artifact-consumption tests for the CAND-004..CAND-007 chain.

These tests exercise real/full artifact shapes, not stripped fixtures, and prove
the pipeline can run from CAND-004 through CAND-007 without symbol mismatch or
unknown-key schema rejection.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas_agent.agent.autonomous_paper_quality import (
    TradingQualityThresholdPolicy,
    build_trading_quality_gate,
    write_trading_quality_artifacts,
)
from atlas_agent.agent.autonomous_paper_shadow_live import (
    build_shadow_live_comparison,
    write_shadow_live_artifacts,
)
from atlas_agent.agent.gated_submit_conformance import (
    SubmitConformanceInputs,
    build_gated_submit_conformance_report,
    write_gated_submit_conformance_artifacts,
)
from atlas_agent.agent.runtime_readiness_envelope import (
    ReadinessEnvelopeInputs,
    build_runtime_readiness_envelope_report,
    write_runtime_readiness_envelope_artifacts,
)


_AS_OF = "2026-06-24T10:00:00Z"
_SYMBOL = "AAPL"
_RUN_ID = "run-e2e-001"


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )


def _make_paper_artifacts(tmp_path: Path) -> Path:
    """Build CAND-004 trading-quality-gate.json with a realistic full shape."""
    out = tmp_path / "cand004"
    out.mkdir()

    metrics = {
        "run_id": _RUN_ID,
        "symbol": _SYMBOL,
        "starting_cash": 10000.0,
        "ending_cash": 10000.98,
        "ending_equity": 10000.98,
        "total_return_pct": 0.0098,
        "max_drawdown_pct": 0.0001,
        "number_of_trades": 1,
        "number_of_fills": 2,
        "number_of_rejections": 1,
        "gross_exposure": 201.0,
        "net_exposure": 0.0,
        "total_commission": 0.02,
        "total_slippage": 0.02,
        "turnover": 0.0201,
        "bars_processed": 10,
        "data_source_redacted": "ohlcv.csv",
        "generated_at": "2026-01-01T00:00:00Z",
    }
    decisions = [
        {"bar_index": 0, "decision_state": "risk_blocked", "risk_result": {"allowed": False}, "symbol": _SYMBOL},
        {"bar_index": 1, "decision_state": "no_trade", "risk_result": {"allowed": True}, "symbol": _SYMBOL},
        {"bar_index": 2, "decision_state": "paper_executed", "risk_result": {"allowed": True}, "symbol": _SYMBOL},
    ]
    fills = [
        {"side": "buy", "quantity": 1.0, "price": 100.0, "notional": 100.0, "commission": 0.01, "slippage": 0.01, "symbol": _SYMBOL},
        {"side": "sell", "quantity": 1.0, "price": 101.0, "notional": 101.0, "commission": 0.01, "slippage": 0.01, "symbol": _SYMBOL},
    ]
    metrics_path = out / "metrics.json"
    decisions_path = out / "decisions.jsonl"
    fills_path = out / "fills.jsonl"
    _write_json(metrics_path, metrics)
    _write_jsonl(decisions_path, decisions)
    _write_jsonl(fills_path, fills)

    gate = build_trading_quality_gate(
        metrics_path=metrics_path,
        decisions_path=decisions_path,
        fills_path=fills_path,
    )
    json_path, _ = write_trading_quality_artifacts(gate, out)
    assert json_path.exists()
    return json_path


def _make_broker_snapshot(tmp_path: Path) -> Path:
    """Build a minimal valid broker snapshot fixture for CAND-005."""
    path = tmp_path / "broker-snapshot.json"
    snapshot = {
        "schema_version": "shadow-live-snapshot.v1",
        "account_label": "simulated-broker",
        "broker_source": "fixture",
        "currency": "USD",
        "cash": 10000.98,
        "equity": 10000.98,
        "buying_power": 10000.98,
        "market_timestamp": "2026-06-24T09:55:00Z",
        "snapshot_freshness_timestamp": "2026-06-24T09:55:00Z",
        "positions": [],
        "open_orders": [],
        "recent_fills": [],
        "completeness_flags": {
            "account": True,
            "positions": True,
            "open_orders": True,
            "recent_fills": True,
            "market_prices": True,
        },
    }
    _write_json(path, snapshot)
    return path


def _make_shadow_live_artifact(quality_gate_path: Path, tmp_path: Path) -> Path:
    """Build CAND-005 shadow-live-comparison.json."""
    snapshot_path = _make_broker_snapshot(tmp_path)
    out = tmp_path / "cand005"
    out.mkdir()
    comparison = build_shadow_live_comparison(
        quality_gate_path=quality_gate_path,
        broker_snapshot_path=snapshot_path,
        output_dir=out,
        now=datetime.fromisoformat("2026-06-24T09:55:00+00:00"),
    )
    assert comparison["status"] == "matched"
    return out / "shadow-live-comparison.json"


def _make_order_intent(tmp_path: Path) -> Path:
    path = tmp_path / "order-intent.json"
    _write_json(
        path,
        {
            "artifact_type": "gated_submit_order_intent",
            "schema_version": "gated-submit-order-intent.v1",
            "intent_kind": "hypothetical",
            "intent_id": "intent-e2e-001",
            "run_id": _RUN_ID,
            "symbol": _SYMBOL,
            "side": "buy",
            "quantity": "1",
            "order_type": "limit",
            "limit_price": "100",
            "time_in_force": "day",
            "created_at": "2026-06-24T09:00:00Z",
        },
    )
    return path


def _make_kill_switch(tmp_path: Path) -> Path:
    path = tmp_path / "kill-switch.json"
    _write_json(
        path,
        {
            "artifact_type": "gated_submit_kill_switch_fixture",
            "schema_version": "gated-submit-kill-switch.v1",
            "fixture_mode": "simulated",
            "scope": "conformance_rehearsal_only",
            "state": "inactive",
            "captured_at": "2026-06-24T09:00:00Z",
            "expires_at": "2026-06-24T11:00:00Z",
        },
    )
    return path


def _make_risk_envelope(tmp_path: Path, order_intent_path: Path) -> Path:
    from atlas_agent.agent.gated_submit_conformance import (
        fingerprint_json as gsc_fingerprint,
    )

    order_intent = json.loads(order_intent_path.read_text(encoding="utf-8"))
    intent_fp = gsc_fingerprint(order_intent)
    path = tmp_path / "risk-envelope.json"
    _write_json(
        path,
        {
            "artifact_type": "gated_submit_risk_envelope_fixture",
            "schema_version": "gated-submit-risk-envelope.v1",
            "fixture_mode": "simulated",
            "represents": "RiskManager_evaluation",
            "evaluation_mode": "paper",
            "intent_fingerprint": intent_fp,
            "captured_at": "2026-06-24T09:00:00Z",
            "expires_at": "2026-06-24T11:00:00Z",
            "decision": "allowed",
            "evaluated_price": "100",
            "evaluated_notional": "100",
            "checks": [{"rule": "max_position_size", "passed": True}],
            "violations": [],
            "limits_digest": "sha256:" + "a" * 64,
            "portfolio_snapshot_digest": "sha256:" + "b" * 64,
        },
    )
    return path


def _make_approval(tmp_path: Path, order_intent_path: Path, risk_envelope_path: Path) -> Path:
    from atlas_agent.agent.gated_submit_conformance import (
        fingerprint_json as gsc_fingerprint,
    )

    order_intent = json.loads(order_intent_path.read_text(encoding="utf-8"))
    risk_envelope = json.loads(risk_envelope_path.read_text(encoding="utf-8"))
    intent_fp = gsc_fingerprint(order_intent)
    risk_fp = gsc_fingerprint(risk_envelope)
    path = tmp_path / "approval.json"
    _write_json(
        path,
        {
            "artifact_type": "gated_submit_approval_fixture",
            "schema_version": "gated-submit-approval-fixture.v1",
            "fixture_mode": "simulated",
            "scope": "conformance_rehearsal_only",
            "fixture_id": "approval-e2e-001",
            "intent_fingerprint": intent_fp,
            "risk_envelope_fingerprint": risk_fp,
            "decision": "approved",
            "actor_label": "simulated-reviewer",
            "approved_at": "2026-06-24T09:00:00Z",
            "expires_at": "2026-06-24T11:00:00Z",
        },
    )
    return path


def _make_gated_submit_conformance_artifact(
    quality_gate_path: Path,
    shadow_comparison_path: Path,
    tmp_path: Path,
) -> Path:
    """Build CAND-006 gated-submit-conformance.json."""
    order_intent_path = _make_order_intent(tmp_path)
    kill_switch_path = _make_kill_switch(tmp_path)
    risk_envelope_path = _make_risk_envelope(tmp_path, order_intent_path)
    approval_path = _make_approval(tmp_path, order_intent_path, risk_envelope_path)

    inputs = SubmitConformanceInputs(
        quality_gate_path=quality_gate_path,
        shadow_comparison_path=shadow_comparison_path,
        order_intent_path=order_intent_path,
        kill_switch_path=kill_switch_path,
        risk_envelope_path=risk_envelope_path,
        approval_path=approval_path,
        output_dir=tmp_path / "cand006" / "out",
        as_of=_AS_OF,
    )
    report = build_gated_submit_conformance_report(inputs)
    recorded = write_gated_submit_conformance_artifacts(report, inputs.output_dir)
    assert recorded.status == "dry_run_recorded"
    assert recorded.symbol == _SYMBOL
    return inputs.output_dir / "gated-submit-conformance.json"


def _make_runtime_envelope_fixture(tmp_path: Path) -> Path:
    path = tmp_path / "runtime-envelope-fixture.json"
    _write_json(
        path,
        {
            "artifact_type": "runtime_readiness_envelope_fixture",
            "schema_version": "runtime-readiness-envelope-fixture.v1",
            "fixture_mode": "simulated/static",
            "run_id": _RUN_ID,
            "symbol": _SYMBOL,
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
        },
    )
    return path


def _make_broker_capabilities(tmp_path: Path) -> Path:
    path = tmp_path / "broker-capabilities.json"
    _write_json(
        path,
        {
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
        },
    )
    return path


def _make_operator_policy(tmp_path: Path) -> Path:
    path = tmp_path / "operator-policy.json"
    _write_json(
        path,
        {
            "artifact_type": "operator_policy_fixture",
            "schema_version": "operator-policy-fixture.v1",
            "requires_manual_review": True,
            "requires_explicit_approval": True,
            "approval_scope": "simulated_only",
            "unattended_operation_allowed": False,
            "max_runtime_window_seconds": 3600,
            "max_actions_per_session": 10,
            "allowed_symbols": [_SYMBOL],
            "blocked_symbols": [],
            "expires_at": "2026-06-24T12:00:00Z",
        },
    )
    return path


def _make_kill_switch_policy(tmp_path: Path) -> Path:
    path = tmp_path / "kill-switch-policy.json"
    _write_json(
        path,
        {
            "artifact_type": "kill_switch_policy_fixture",
            "schema_version": "kill-switch-policy-fixture.v1",
            "kill_switch_required": True,
            "default_state_on_missing_runtime": "blocked",
            "default_state_on_unknown_runtime": "blocked",
            "operator_override_allowed": False,
            "expires_at": "2026-06-24T12:00:00Z",
        },
    )
    return path


def _make_audit_policy(tmp_path: Path) -> Path:
    path = tmp_path / "audit-policy.json"
    _write_json(
        path,
        {
            "artifact_type": "audit_policy_fixture",
            "schema_version": "audit-policy-fixture.v1",
            "audit_required": True,
            "append_only_required": True,
            "hash_chain_required": True,
            "local_artifact_recording_required": True,
            "live_audit_chain_claimed": False,
            "expires_at": "2026-06-24T12:00:00Z",
        },
    )
    return path


def _make_runtime_readiness_envelope_artifact(
    quality_gate_path: Path,
    shadow_comparison_path: Path,
    submit_conformance_path: Path,
    tmp_path: Path,
) -> Path:
    """Build CAND-007 runtime-readiness-envelope.json."""
    inputs = ReadinessEnvelopeInputs(
        quality_gate_path=quality_gate_path,
        shadow_comparison_path=shadow_comparison_path,
        submit_conformance_path=submit_conformance_path,
        runtime_envelope_path=_make_runtime_envelope_fixture(tmp_path),
        broker_capabilities_path=_make_broker_capabilities(tmp_path),
        operator_policy_path=_make_operator_policy(tmp_path),
        kill_switch_policy_path=_make_kill_switch_policy(tmp_path),
        audit_policy_path=_make_audit_policy(tmp_path),
        output_dir=tmp_path / "cand007" / "out",
        as_of=_AS_OF,
    )
    report = build_runtime_readiness_envelope_report(inputs)
    recorded = write_runtime_readiness_envelope_artifacts(report, inputs.output_dir)
    assert recorded.status == "readiness_envelope_recorded"
    assert recorded.symbol == _SYMBOL
    return inputs.output_dir / "runtime-readiness-envelope.json"


def test_cand004_symbol_is_ticker_not_data_source(tmp_path: Path) -> None:
    quality_gate_path = _make_paper_artifacts(tmp_path)
    data = json.loads(quality_gate_path.read_text(encoding="utf-8"))
    assert data["symbol"] == _SYMBOL
    assert data["metrics"]["data_source_redacted"] == "ohlcv.csv"
    assert data["metrics"]["data_source_redacted"] != _SYMBOL


def test_cand004_symbol_propagates_to_cand005(tmp_path: Path) -> None:
    quality_gate_path = _make_paper_artifacts(tmp_path)
    shadow_path = _make_shadow_live_artifact(quality_gate_path, tmp_path)
    data = json.loads(shadow_path.read_text(encoding="utf-8"))
    assert data["symbol"] == _SYMBOL
    assert data["quality_state"] == "eligible_for_shadow_live_quality_review"
    assert data["status"] == "matched"


def test_cand004_symbol_propagates_to_cand006(tmp_path: Path) -> None:
    quality_gate_path = _make_paper_artifacts(tmp_path)
    shadow_path = _make_shadow_live_artifact(quality_gate_path, tmp_path)
    conformance_path = _make_gated_submit_conformance_artifact(
        quality_gate_path, shadow_path, tmp_path
    )
    data = json.loads(conformance_path.read_text(encoding="utf-8"))
    assert data["symbol"] == _SYMBOL
    assert data["status"] == "dry_run_recorded"
    assert data["quality_gate_summary"]["quality_state"] == "eligible_for_shadow_live_quality_review"


def test_cand004_symbol_propagates_to_cand007(tmp_path: Path) -> None:
    quality_gate_path = _make_paper_artifacts(tmp_path)
    shadow_path = _make_shadow_live_artifact(quality_gate_path, tmp_path)
    conformance_path = _make_gated_submit_conformance_artifact(
        quality_gate_path, shadow_path, tmp_path
    )
    envelope_path = _make_runtime_readiness_envelope_artifact(
        quality_gate_path, shadow_path, conformance_path, tmp_path
    )
    data = json.loads(envelope_path.read_text(encoding="utf-8"))
    assert data["symbol"] == _SYMBOL
    assert data["status"] == "readiness_envelope_recorded"
    assert data["upstream_summaries"]["cand004"]["quality_state"] == "eligible_for_shadow_live_quality_review"


def test_full_cand004_artifact_accepted_by_cand006(tmp_path: Path) -> None:
    quality_gate_path = _make_paper_artifacts(tmp_path)
    shadow_path = _make_shadow_live_artifact(quality_gate_path, tmp_path)
    conformance_path = _make_gated_submit_conformance_artifact(
        quality_gate_path, shadow_path, tmp_path
    )
    data = json.loads(conformance_path.read_text(encoding="utf-8"))
    assert data["status"] == "dry_run_recorded"
    assert data["exit_code"] == 0


def test_full_cand005_artifact_accepted_by_cand006(tmp_path: Path) -> None:
    quality_gate_path = _make_paper_artifacts(tmp_path)
    shadow_path = _make_shadow_live_artifact(quality_gate_path, tmp_path)
    # Ensure the shadow comparison artifact contains extra upstream fields.
    shadow_data = json.loads(shadow_path.read_text(encoding="utf-8"))
    assert "broker_snapshot_summary" in shadow_data
    assert "divergence_results" in shadow_data
    conformance_path = _make_gated_submit_conformance_artifact(
        quality_gate_path, shadow_path, tmp_path
    )
    data = json.loads(conformance_path.read_text(encoding="utf-8"))
    assert data["status"] == "dry_run_recorded"


def test_full_upstream_artifacts_accepted_by_cand007(tmp_path: Path) -> None:
    quality_gate_path = _make_paper_artifacts(tmp_path)
    shadow_path = _make_shadow_live_artifact(quality_gate_path, tmp_path)
    conformance_path = _make_gated_submit_conformance_artifact(
        quality_gate_path, shadow_path, tmp_path
    )
    envelope_path = _make_runtime_readiness_envelope_artifact(
        quality_gate_path, shadow_path, conformance_path, tmp_path
    )
    data = json.loads(envelope_path.read_text(encoding="utf-8"))
    assert data["status"] == "readiness_envelope_recorded"
    assert data["exit_code"] == 0
    assert "blockers" in data
    assert data["blockers"] == []


def test_end_to_end_cand004_to_cand007_pipeline(tmp_path: Path) -> None:
    """Full pipeline: CAND-004 -> CAND-005 -> CAND-006 -> CAND-007."""
    quality_gate_path = _make_paper_artifacts(tmp_path)
    shadow_path = _make_shadow_live_artifact(quality_gate_path, tmp_path)
    conformance_path = _make_gated_submit_conformance_artifact(
        quality_gate_path, shadow_path, tmp_path
    )
    envelope_path = _make_runtime_readiness_envelope_artifact(
        quality_gate_path, shadow_path, conformance_path, tmp_path
    )

    quality_gate = json.loads(quality_gate_path.read_text(encoding="utf-8"))
    shadow = json.loads(shadow_path.read_text(encoding="utf-8"))
    conformance = json.loads(conformance_path.read_text(encoding="utf-8"))
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))

    # Symbol propagated end-to-end.
    assert quality_gate["symbol"] == _SYMBOL
    assert shadow["symbol"] == _SYMBOL
    assert conformance["symbol"] == _SYMBOL
    assert envelope["symbol"] == _SYMBOL

    # No schema/unknown-key rejection occurred.
    assert conformance["status"] == "dry_run_recorded"
    assert envelope["status"] == "readiness_envelope_recorded"

    # Safety assertions remain conservative.
    assert conformance["safety_assertions"]["no_live_submit"] is True
    assert conformance["safety_assertions"]["no_broker_called"] is True
    assert envelope["envelope_assertions"]["live_submit_forbidden"] is True
