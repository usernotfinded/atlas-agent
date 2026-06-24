import json
from pathlib import Path

from atlas_agent.agent.autonomous_paper_quality import build_trading_quality_gate, TradingQualityThresholdPolicy


def _write_artifacts(tmp_path: Path, metrics: dict, decisions: list, fills: list):
    (tmp_path / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    (tmp_path / "decisions.jsonl").write_text(
        "\n".join(json.dumps(d) for d in decisions), encoding="utf-8"
    )
    (tmp_path / "fills.jsonl").write_text(
        "\n".join(json.dumps(f) for f in fills), encoding="utf-8"
    )


def test_missing_metrics_fail_closed(tmp_path: Path):
    result = build_trading_quality_gate(
        metrics_path=str(tmp_path / "missing.json"),
        decisions_path=str(tmp_path / "missing.jsonl"),
        fills_path=str(tmp_path / "missing.jsonl"),
    )
    assert result["quality_state"] == "not_evaluated"
    assert any("metrics" in e.lower() for e in result["blockers"])


def test_default_threshold_policy_is_conservative():
    policy = TradingQualityThresholdPolicy()
    assert policy.min_bars_processed == 10
    assert policy.min_fills == 1
    assert policy.min_no_trade_decisions == 1
    assert policy.min_risk_rejections == 1
    assert policy.max_drawdown_pct == 50.0
    assert policy.max_exposure_pct == 200.0
    assert policy.max_turnover == 100.0
    assert policy.max_cost_impact_pct == 10.0
    assert policy.min_data_coverage == 0.5
    assert policy.max_invalid_metric_count == 0


def test_policy_roundtrips_through_dict():
    original = TradingQualityThresholdPolicy(min_bars_processed=42)
    restored = TradingQualityThresholdPolicy.from_dict(original.to_dict())
    assert restored == original


def _minimal_valid_fixtures():
    decisions = [
        {"bar_index": 0, "decision_state": "risk_blocked", "risk_result": {"allowed": False}},
        {"bar_index": 1, "decision_state": "no_trade", "risk_result": {"allowed": True}},
        {"bar_index": 2, "decision_state": "paper_executed", "risk_result": {"allowed": True}},
    ]
    fills = [
        {"side": "buy", "quantity": 1.0, "price": 100.0, "notional": 100.0, "commission": 0.01, "slippage": 0.01},
        {"side": "sell", "quantity": 1.0, "price": 101.0, "notional": 101.0, "commission": 0.01, "slippage": 0.01},
    ]
    metrics = {
        "run_id": "r1",
        "starting_cash": 10000.0,
        "ending_cash": 10000.99,
        "ending_equity": 10000.99,
        "total_return_pct": 0.0099,
        "max_drawdown_pct": 0.0,
        "number_of_trades": 1,
        "number_of_fills": 2,
        "number_of_rejections": 1,
        "gross_exposure": 201.0,
        "net_exposure": 0.0,
        "total_commission": 0.02,
        "total_slippage": 0.02,
        "turnover": 0.0201,
        "bars_processed": 10,
        "data_source_redacted": "demo.csv",
        "generated_at": "2026-01-01T00:00:00Z",
    }
    return metrics, decisions, fills


def test_no_fills_blocked(tmp_path: Path):
    metrics, decisions, _ = _minimal_valid_fixtures()
    metrics["number_of_fills"] = 0
    _write_artifacts(tmp_path, metrics, decisions, [])
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
    )
    assert result["quality_state"] == "blocked"
    trade_dim = next(d for d in result["dimensions"] if d["name"] == "trade_activity")
    assert not trade_dim["passed"]
