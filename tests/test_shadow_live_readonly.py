from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from atlas_agent.agent.autonomous_paper_shadow_live import (
    BrokerAccountSnapshot,
    BrokerFillSnapshot,
    BrokerOrderSnapshot,
    BrokerPositionSnapshot,
    ShadowLiveThresholdPolicy,
    build_shadow_live_comparison,
    compare_paper_to_broker,
    load_broker_snapshot,
    load_quality_gate,
    resolve_shadow_live_status,
    write_shadow_live_artifacts,
)

_FIXED_NOW = datetime.fromisoformat("2026-06-23T12:10:00+00:00")


def _make_minimal_snapshot() -> dict:
    return {
        "schema_version": "shadow-live-snapshot.v1",
        "account_label": "paper-shadow-001",
        "broker_source": "fixture",
        "currency": "USD",
        "cash": 10000.0,
        "equity": 10500.0,
        "buying_power": 20000.0,
        "market_timestamp": "2026-06-23T12:00:00Z",
        "snapshot_freshness_timestamp": "2026-06-23T12:05:00Z",
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


def _make_snapshot_with_position(
    symbol: str = "AAPL",
    quantity: float = 10,
    side: str = "long",
    market_price: float = 155.0,
    market_value: float = 1550.0,
) -> dict:
    snapshot = _make_minimal_snapshot()
    snapshot["positions"] = [
        {
            "symbol": symbol,
            "quantity": quantity,
            "side": side,
            "average_price": 150.0,
            "market_price": market_price,
            "market_value": market_value,
        }
    ]
    return snapshot


def _make_eligible_gate() -> dict:
    return {
        "artifact_type": "trading_quality_gate",
        "schema_version": "trading-quality-gate.v1",
        "mode": "paper",
        "run_id": "run-123",
        "symbol": "AAPL",
        "quality_state": "eligible_for_shadow_live_quality_review",
        "blockers": [],
        "dimensions": [],
        "metrics": {
            "ending_cash": 10000.0,
            "ending_equity": 10500.0,
            "number_of_fills": 2,
            "bars_processed": 50,
        },
        "threshold_policy": {},
        "input_artifacts": {},
        "disclaimer": "...",
    }


def _make_broker_account_snapshot(
    *,
    positions: tuple[BrokerPositionSnapshot, ...] = (),
    open_orders: tuple[BrokerOrderSnapshot, ...] = (),
    recent_fills: tuple[BrokerFillSnapshot, ...] = (),
    completeness_flags: dict[str, bool] | None = None,
    snapshot_freshness_timestamp: str = "2026-06-23T12:05:00Z",
    cash: float = 10000.0,
    equity: float = 10500.0,
    buying_power: float = 20000.0,
) -> BrokerAccountSnapshot:
    if completeness_flags is None:
        completeness_flags = {
            "account": True,
            "positions": True,
            "open_orders": True,
            "recent_fills": True,
            "market_prices": True,
        }
    return BrokerAccountSnapshot(
        schema_version="shadow-live-snapshot.v1",
        account_label="paper-shadow-001",
        broker_source="fixture",
        currency="USD",
        cash=cash,
        equity=equity,
        buying_power=buying_power,
        market_timestamp="2026-06-23T12:00:00Z",
        snapshot_freshness_timestamp=snapshot_freshness_timestamp,
        positions=positions,
        open_orders=open_orders,
        recent_fills=recent_fills,
        completeness_flags=completeness_flags,
    )


def test_load_broker_snapshot_minimal(tmp_path: Path) -> None:
    snapshot = _make_snapshot_with_position()
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot))
    result, errors = load_broker_snapshot(path)
    assert result is not None
    assert not errors
    assert result.account_label == "paper-shadow-001"
    assert len(result.positions) == 1
    assert result.positions[0].quantity == 10
    assert result.positions[0].side == "long"


def test_load_broker_snapshot_malformed_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "snapshot.json"
    path.write_text("not json")
    result, errors = load_broker_snapshot(path)
    assert result is None
    assert errors
    assert "not valid JSON" in " ".join(errors)


def test_load_broker_snapshot_missing_required_field(tmp_path: Path) -> None:
    snapshot = _make_minimal_snapshot()
    del snapshot["equity"]
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot))
    result, errors = load_broker_snapshot(path)
    assert result is None
    assert any("equity" in e for e in errors)


def test_load_broker_snapshot_invalid_finite_check(tmp_path: Path) -> None:
    snapshot = _make_minimal_snapshot()
    snapshot["cash"] = float("inf")
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot))
    result, errors = load_broker_snapshot(path)
    assert result is None
    assert any("finite" in e.lower() for e in errors)


def test_load_broker_snapshot_rejects_bad_schema_version(tmp_path: Path) -> None:
    snapshot = _make_minimal_snapshot()
    snapshot["schema_version"] = "shadow-live-snapshot.v0"
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot))
    result, errors = load_broker_snapshot(path)
    assert result is None
    assert any("schema_version" in e for e in errors)


def test_load_broker_snapshot_rejects_invalid_market_timestamp(tmp_path: Path) -> None:
    snapshot = _make_minimal_snapshot()
    snapshot["market_timestamp"] = "not-a-timestamp"
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot))
    result, errors = load_broker_snapshot(path)
    assert result is None
    assert any("market_timestamp" in e for e in errors)


def test_load_broker_snapshot_rejects_invalid_filled_at(tmp_path: Path) -> None:
    snapshot = _make_minimal_snapshot()
    snapshot["recent_fills"] = [
        {
            "fill_id": "fill-1",
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 5,
            "price": 150.0,
            "filled_at": "not-a-timestamp",
        }
    ]
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot))
    result, errors = load_broker_snapshot(path)
    assert result is None
    assert any("filled_at" in e for e in errors)


def test_load_quality_gate_eligible(tmp_path: Path) -> None:
    gate = _make_eligible_gate()
    path = tmp_path / "gate.json"
    path.write_text(json.dumps(gate))
    result, errors = load_quality_gate(path)
    assert result is not None
    assert not errors
    assert result["quality_state"] == "eligible_for_shadow_live_quality_review"


def test_load_quality_gate_malformed(tmp_path: Path) -> None:
    path = tmp_path / "gate.json"
    path.write_text("{broken")
    result, errors = load_quality_gate(path)
    assert result is None
    assert errors


def test_load_quality_gate_rejects_non_paper_mode(tmp_path: Path) -> None:
    gate = _make_eligible_gate()
    gate["mode"] = "live"
    path = tmp_path / "gate.json"
    path.write_text(json.dumps(gate))
    result, errors = load_quality_gate(path)
    assert result is None
    assert any("mode" in e for e in errors)


def test_compare_matched() -> None:
    paper_state: dict[str, Any] = {
        "cash": 10000.0,
        "equity": 10500.0,
        "buying_power": None,
        "positions": [],
    }
    snapshot = _make_broker_account_snapshot()
    policy = ShadowLiveThresholdPolicy()
    result = compare_paper_to_broker(paper_state, snapshot, policy)
    assert result["cash_difference"] == 0.0
    assert result["equity_difference"] == 0.0
    status, _ = resolve_shadow_live_status(result, snapshot, policy, now=_FIXED_NOW)
    assert status == "matched"


def test_compare_minor_divergence_cash() -> None:
    paper_state: dict[str, Any] = {
        "cash": 10110.0,
        "equity": 10500.0,
        "buying_power": None,
        "positions": [],
    }
    snapshot = _make_broker_account_snapshot()
    policy = ShadowLiveThresholdPolicy()
    result = compare_paper_to_broker(paper_state, snapshot, policy)
    status, _ = resolve_shadow_live_status(result, snapshot, policy, now=_FIXED_NOW)
    assert status == "minor_divergence"


def test_compare_major_divergence_equity() -> None:
    paper_state: dict[str, Any] = {
        "cash": 10000.0,
        "equity": 12000.0,
        "buying_power": None,
        "positions": [],
    }
    snapshot = _make_broker_account_snapshot()
    policy = ShadowLiveThresholdPolicy()
    result = compare_paper_to_broker(paper_state, snapshot, policy)
    status, _ = resolve_shadow_live_status(result, snapshot, policy, now=_FIXED_NOW)
    assert status == "major_divergence"


def test_compare_major_divergence_position_quantity() -> None:
    paper_state: dict[str, Any] = {
        "cash": 10000.0,
        "equity": 10500.0,
        "buying_power": None,
        "positions": [
            {"symbol": "AAPL", "quantity": 10, "side": "long", "market_value": 1550.0}
        ],
    }
    snapshot = _make_broker_account_snapshot(
        positions=(
            BrokerPositionSnapshot(
                symbol="AAPL",
                quantity=1,
                side="long",
                average_price=150.0,
                market_price=155.0,
                market_value=155.0,
            ),
        ),
    )
    policy = ShadowLiveThresholdPolicy()
    result = compare_paper_to_broker(paper_state, snapshot, policy)
    status, _ = resolve_shadow_live_status(result, snapshot, policy, now=_FIXED_NOW)
    assert status == "major_divergence"


def test_incomplete_snapshot_missing_critical_flag() -> None:
    paper_state: dict[str, Any] = {
        "cash": 10000.0,
        "equity": 10500.0,
        "buying_power": None,
        "positions": [],
    }
    snapshot = _make_broker_account_snapshot(
        completeness_flags={
            "account": True,
            "positions": False,
            "open_orders": True,
            "recent_fills": True,
            "market_prices": True,
        },
    )
    policy = ShadowLiveThresholdPolicy()
    result = compare_paper_to_broker(paper_state, snapshot, policy)
    status, blockers = resolve_shadow_live_status(
        result, snapshot, policy, now=_FIXED_NOW
    )
    assert status == "incomplete_snapshot"
    assert any("positions" in b for b in blockers)


def test_stale_snapshot() -> None:
    paper_state: dict[str, Any] = {
        "cash": 10000.0,
        "equity": 10500.0,
        "buying_power": None,
        "positions": [],
    }
    snapshot = _make_broker_account_snapshot(
        snapshot_freshness_timestamp="2026-06-23T11:00:00Z",
    )
    policy = ShadowLiveThresholdPolicy()
    now = datetime.fromisoformat("2026-06-23T12:10:00+00:00")
    result = compare_paper_to_broker(paper_state, snapshot, policy)
    status, blockers = resolve_shadow_live_status(result, snapshot, policy, now=now)
    assert status == "stale_snapshot"
    assert any("age" in b for b in blockers)


def test_build_shadow_live_comparison_blocked_by_quality_gate(tmp_path: Path) -> None:
    gate = _make_eligible_gate()
    gate["quality_state"] = "blocked"
    gate["blockers"] = ["drawdown too high"]
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps(gate))
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(_make_minimal_snapshot()))
    report = build_shadow_live_comparison(
        quality_gate_path=gate_path,
        broker_snapshot_path=snapshot_path,
        output_dir=tmp_path / "out",
        now=_FIXED_NOW,
    )
    assert report["status"] == "blocked"


def test_build_shadow_live_comparison_matched(tmp_path: Path) -> None:
    gate = _make_eligible_gate()
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps(gate))
    snapshot = _make_minimal_snapshot()
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot))
    report = build_shadow_live_comparison(
        quality_gate_path=gate_path,
        broker_snapshot_path=snapshot_path,
        output_dir=tmp_path / "out",
        now=_FIXED_NOW,
    )
    assert report["status"] == "matched"
    assert report["artifact_type"] == "shadow_live_comparison"


def test_build_shadow_live_comparison_minor_divergence(tmp_path: Path) -> None:
    gate = _make_eligible_gate()
    gate["metrics"]["ending_cash"] = 10110.0
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps(gate))
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(_make_minimal_snapshot()))
    report = build_shadow_live_comparison(
        quality_gate_path=gate_path,
        broker_snapshot_path=snapshot_path,
        output_dir=tmp_path / "out",
        now=_FIXED_NOW,
    )
    assert report["status"] == "minor_divergence"


def test_build_shadow_live_comparison_major_divergence(tmp_path: Path) -> None:
    gate = _make_eligible_gate()
    gate["metrics"]["ending_equity"] = 12000.0
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps(gate))
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(_make_minimal_snapshot()))
    report = build_shadow_live_comparison(
        quality_gate_path=gate_path,
        broker_snapshot_path=snapshot_path,
        output_dir=tmp_path / "out",
        now=_FIXED_NOW,
    )
    assert report["status"] == "major_divergence"


def test_build_shadow_live_comparison_incomplete_snapshot(tmp_path: Path) -> None:
    gate = _make_eligible_gate()
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps(gate))
    snapshot = _make_minimal_snapshot()
    snapshot["completeness_flags"]["market_prices"] = False
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot))
    report = build_shadow_live_comparison(
        quality_gate_path=gate_path,
        broker_snapshot_path=snapshot_path,
        output_dir=tmp_path / "out",
        now=_FIXED_NOW,
    )
    assert report["status"] == "incomplete_snapshot"


def test_build_shadow_live_comparison_stale_snapshot(tmp_path: Path) -> None:
    gate = _make_eligible_gate()
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps(gate))
    snapshot = _make_minimal_snapshot()
    snapshot["snapshot_freshness_timestamp"] = "2026-06-23T11:00:00Z"
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot))
    now = datetime.fromisoformat("2026-06-23T12:10:00+00:00")
    report = build_shadow_live_comparison(
        quality_gate_path=gate_path,
        broker_snapshot_path=snapshot_path,
        output_dir=tmp_path / "out",
        now=now,
    )
    assert report["status"] == "stale_snapshot"


def test_build_shadow_live_comparison_malformed_snapshot(tmp_path: Path) -> None:
    gate = _make_eligible_gate()
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps(gate))
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text("not json")
    report = build_shadow_live_comparison(
        quality_gate_path=gate_path,
        broker_snapshot_path=snapshot_path,
        output_dir=tmp_path / "out",
        now=_FIXED_NOW,
    )
    assert report["status"] == "blocked"


def test_build_shadow_live_comparison_blocks_bad_quality_gate_schema_version(
    tmp_path: Path,
) -> None:
    gate = _make_eligible_gate()
    gate["schema_version"] = "trading-quality-gate.v0"
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps(gate))
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(_make_minimal_snapshot()))
    report = build_shadow_live_comparison(
        quality_gate_path=gate_path,
        broker_snapshot_path=snapshot_path,
        output_dir=tmp_path / "out",
        now=_FIXED_NOW,
    )
    assert report["status"] == "blocked"


def test_build_shadow_live_comparison_blocks_bad_quality_gate_artifact_type(
    tmp_path: Path,
) -> None:
    gate = _make_eligible_gate()
    gate["artifact_type"] = "trading_quality_gate_bad"
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps(gate))
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(_make_minimal_snapshot()))
    report = build_shadow_live_comparison(
        quality_gate_path=gate_path,
        broker_snapshot_path=snapshot_path,
        output_dir=tmp_path / "out",
        now=_FIXED_NOW,
    )
    assert report["status"] == "blocked"


def test_build_shadow_live_comparison_not_evaluated_insufficient_paper_data(
    tmp_path: Path,
) -> None:
    gate = _make_eligible_gate()
    gate["metrics"] = {}
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps(gate))
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(_make_minimal_snapshot()))
    report = build_shadow_live_comparison(
        quality_gate_path=gate_path,
        broker_snapshot_path=snapshot_path,
        output_dir=tmp_path / "out",
        now=_FIXED_NOW,
    )
    assert report["status"] == "not_evaluated"
    assert any("insufficient paper-side data" in b for b in report["blockers"])


def test_artifact_writers_produce_files(tmp_path: Path) -> None:
    gate = _make_eligible_gate()
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps(gate))
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(_make_minimal_snapshot()))
    output_dir = tmp_path / "out"
    report = build_shadow_live_comparison(
        quality_gate_path=gate_path,
        broker_snapshot_path=snapshot_path,
        output_dir=output_dir,
        now=_FIXED_NOW,
    )
    write_shadow_live_artifacts(report, output_dir)
    json_path = output_dir / "shadow-live-comparison.json"
    md_path = output_dir / "shadow-live-report.md"
    assert json_path.exists()
    assert md_path.exists()
    json_data = json.loads(json_path.read_text())
    assert json_data["status"] == "matched"
    md_text = md_path.read_text()
    assert "read-only" in md_text.lower()
    assert report["disclaimer"] in md_text


def test_input_files_not_mutated(tmp_path: Path) -> None:
    def _file_hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    gate = _make_eligible_gate()
    snapshot = _make_minimal_snapshot()
    gate_path = tmp_path / "gate.json"
    snap_path = tmp_path / "snapshot.json"
    gate_path.write_text(json.dumps(gate))
    snap_path.write_text(json.dumps(snapshot))
    gate_hash = _file_hash(gate_path)
    snap_hash = _file_hash(snap_path)
    build_shadow_live_comparison(
        quality_gate_path=gate_path,
        broker_snapshot_path=snap_path,
        output_dir=tmp_path / "out",
        now=_FIXED_NOW,
    )
    assert _file_hash(gate_path) == gate_hash
    assert _file_hash(snap_path) == snap_hash


def test_path_redaction_in_artifacts(tmp_path: Path) -> None:
    gate = _make_eligible_gate()
    gate_path = tmp_path / "nested" / "gate.json"
    gate_path.parent.mkdir(parents=True)
    gate_path.write_text(json.dumps(gate))
    snapshot_path = tmp_path / "nested" / "snapshot.json"
    snapshot_path.write_text(json.dumps(_make_minimal_snapshot()))
    output_dir = tmp_path / "out"
    report = build_shadow_live_comparison(
        quality_gate_path=gate_path,
        broker_snapshot_path=snapshot_path,
        output_dir=output_dir,
        now=_FIXED_NOW,
    )
    assert report["input_artifacts"]["quality_gate"] == "gate.json"
    assert report["input_artifacts"]["broker_snapshot"] == "snapshot.json"
    json_data = json.loads((output_dir / "shadow-live-comparison.json").read_text())
    assert json_data["input_artifacts"]["quality_gate"] == "gate.json"


def test_write_shadow_live_artifacts_redacts_absolute_paths(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    report = _make_eligible_gate()
    report["artifact_type"] = "shadow_live_comparison"
    report["schema_version"] = "shadow-live-comparison.v1"
    report["status"] = "matched"
    report["input_artifacts"] = {
        "quality_gate": str(tmp_path / "secret" / "gate.json"),
        "broker_snapshot": str(tmp_path / "secret" / "snapshot.json"),
        "state": str(tmp_path / "secret" / "state.json"),
    }
    original_inputs = dict(report["input_artifacts"])
    write_shadow_live_artifacts(report, output_dir)
    json_data = json.loads((output_dir / "shadow-live-comparison.json").read_text())
    assert json_data["input_artifacts"]["quality_gate"] == "gate.json"
    assert json_data["input_artifacts"]["broker_snapshot"] == "snapshot.json"
    assert json_data["input_artifacts"]["state"] == "state.json"
    assert report["input_artifacts"] == original_inputs


def test_open_orders_incomplete_not_blocking(tmp_path: Path) -> None:
    gate = _make_eligible_gate()
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps(gate))
    snapshot = _make_minimal_snapshot()
    snapshot["completeness_flags"]["open_orders"] = False
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot))
    report = build_shadow_live_comparison(
        quality_gate_path=gate_path,
        broker_snapshot_path=snapshot_path,
        output_dir=tmp_path / "out",
        now=_FIXED_NOW,
    )
    assert report["status"] == "matched"
    assert report["divergence_results"]["open_order_differences"]["available"] is False


def test_open_order_differences_detected() -> None:
    paper_state: dict[str, Any] = {
        "cash": 10000.0,
        "equity": 10500.0,
        "buying_power": None,
        "positions": [],
        "open_orders": [
            {
                "order_id": "order-1",
                "symbol": "AAPL",
                "side": "buy",
                "order_type": "limit",
                "quantity": 5,
                "filled_quantity": 0,
                "limit_price": 150.0,
                "status": "open",
            }
        ],
    }
    snapshot = _make_broker_account_snapshot(
        open_orders=(
            BrokerOrderSnapshot(
                order_id="order-1",
                symbol="AAPL",
                side="buy",
                order_type="limit",
                quantity=10,
                filled_quantity=0,
                limit_price=150.0,
                status="open",
            ),
        ),
    )
    policy = ShadowLiveThresholdPolicy()
    result = compare_paper_to_broker(paper_state, snapshot, policy)
    assert result["open_order_differences"]["available"] is True
    assert len(result["open_order_differences"]["differences"]) == 1


def test_fill_differences_detected() -> None:
    paper_state: dict[str, Any] = {
        "cash": 10000.0,
        "equity": 10500.0,
        "buying_power": None,
        "positions": [],
        "fills": [
            {
                "fill_id": "fill-1",
                "order_id": "order-1",
                "symbol": "AAPL",
                "side": "buy",
                "quantity": 5,
                "price": 150.0,
                "filled_at": "2026-06-23T12:00:00Z",
            }
        ],
    }
    snapshot = _make_broker_account_snapshot(
        recent_fills=(
            BrokerFillSnapshot(
                fill_id="fill-1",
                order_id="order-1",
                symbol="AAPL",
                side="buy",
                quantity=10,
                price=150.0,
                filled_at="2026-06-23T12:00:00Z",
            ),
        ),
    )
    policy = ShadowLiveThresholdPolicy()
    result = compare_paper_to_broker(paper_state, snapshot, policy)
    assert result["fill_differences"]["available"] is True
    assert len(result["fill_differences"]["differences"]) == 1


def test_paper_only_and_broker_only_positions() -> None:
    paper_state: dict[str, Any] = {
        "cash": 10000.0,
        "equity": 10500.0,
        "buying_power": None,
        "positions": [
            {"symbol": "AAPL", "quantity": 10, "side": "long", "market_value": 1550.0}
        ],
    }
    snapshot = _make_broker_account_snapshot(
        positions=(
            BrokerPositionSnapshot(
                symbol="TSLA",
                quantity=5,
                side="short",
                average_price=700.0,
                market_price=710.0,
                market_value=-3550.0,
            ),
        ),
    )
    policy = ShadowLiveThresholdPolicy()
    result = compare_paper_to_broker(paper_state, snapshot, policy)
    by_symbol = {p["symbol"]: p for p in result["position_differences"]}
    assert by_symbol["AAPL"]["paper_only"] is True
    assert by_symbol["TSLA"]["broker_only"] is True
    assert by_symbol["TSLA"]["quantity_difference"] == 5


def test_signed_quantity_short_position() -> None:
    paper_state: dict[str, Any] = {
        "cash": 10000.0,
        "equity": 10500.0,
        "buying_power": None,
        "positions": [
            {"symbol": "TSLA", "quantity": 5, "side": "short", "market_value": -3550.0}
        ],
    }
    snapshot = _make_broker_account_snapshot(
        positions=(
            BrokerPositionSnapshot(
                symbol="TSLA",
                quantity=5,
                side="short",
                average_price=700.0,
                market_price=710.0,
                market_value=-3550.0,
            ),
        ),
    )
    policy = ShadowLiveThresholdPolicy()
    result = compare_paper_to_broker(paper_state, snapshot, policy)
    assert result["position_differences"][0]["quantity_difference"] == 0.0


def test_threshold_policy_to_dict_roundtrip() -> None:
    policy = ShadowLiveThresholdPolicy(
        minor_cash_pct=2.0,
        major_cash_pct=10.0,
        max_snapshot_age_seconds=600.0,
    )
    data = policy.to_dict()
    assert data["minor_cash_pct"] == 2.0
    assert data["major_cash_pct"] == 10.0
    assert data["max_snapshot_age_seconds"] == 600.0


def test_threshold_policy_from_dict_rejects_non_numeric() -> None:
    with pytest.raises(ValueError, match="must be a finite number"):
        ShadowLiveThresholdPolicy.from_dict({"minor_cash_pct": "not-a-number"})


def test_not_evaluated_quality_gate(tmp_path: Path) -> None:
    gate = _make_eligible_gate()
    gate["quality_state"] = "not_evaluated"
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps(gate))
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(_make_minimal_snapshot()))
    report = build_shadow_live_comparison(
        quality_gate_path=gate_path,
        broker_snapshot_path=snapshot_path,
        output_dir=tmp_path / "out",
        now=_FIXED_NOW,
    )
    assert report["status"] == "not_evaluated"
