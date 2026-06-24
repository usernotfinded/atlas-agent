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
