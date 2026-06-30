import json
import subprocess
from pathlib import Path

from atlas_agent.agent.autonomous_paper_quality import build_trading_quality_gate, TradingQualityThresholdPolicy, write_trading_quality_artifacts


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
        {"side": "buy", "quantity": 1.0, "price": 100.0, "notional": 100.0, "commission": 0.01, "slippage": 0.01, "symbol": "DEMO-SYMBOL"},
        {"side": "sell", "quantity": 1.0, "price": 101.0, "notional": 101.0, "commission": 0.01, "slippage": 0.01, "symbol": "DEMO-SYMBOL"},
    ]
    metrics = {
        "run_id": "r1",
        "symbol": "DEMO-SYMBOL",
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


def test_malformed_metrics_fail_closed(tmp_path: Path):
    (tmp_path / "metrics.json").write_text("not json", encoding="utf-8")
    (tmp_path / "decisions.jsonl").write_text("{}", encoding="utf-8")
    (tmp_path / "fills.jsonl").write_text("{}", encoding="utf-8")
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
    )
    assert result["quality_state"] == "not_evaluated"


def test_missing_decisions_fail_closed(tmp_path: Path):
    metrics, _, fills = _minimal_valid_fixtures()
    _write_artifacts(tmp_path, metrics, [], fills)
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
    )
    assert result["quality_state"] == "blocked"
    artifact_dim = next(d for d in result["dimensions"] if d["name"] == "artifact_integrity")
    assert not artifact_dim["passed"]


def test_no_risk_rejections_blocked(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    decisions = [d for d in decisions if d["decision_state"] != "risk_blocked"]
    _write_artifacts(tmp_path, metrics, decisions, fills)
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
    )
    dim = next(d for d in result["dimensions"] if d["name"] == "risk_rejection_coverage")
    assert not dim["passed"]


def test_no_no_trade_decisions_blocked(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    decisions = [d for d in decisions if d["decision_state"] != "no_trade"]
    _write_artifacts(tmp_path, metrics, decisions, fills)
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
    )
    dim = next(d for d in result["dimensions"] if d["name"] == "no_trade_coverage")
    assert not dim["passed"]


def test_drawdown_above_threshold_blocks(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    metrics["max_drawdown_pct"] = 60.0
    _write_artifacts(tmp_path, metrics, decisions, fills)
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
        policy=TradingQualityThresholdPolicy(max_drawdown_pct=50.0),
    )
    dim = next(d for d in result["dimensions"] if d["name"] == "drawdown_bounds")
    assert not dim["passed"]


def test_exposure_above_threshold_blocks(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    metrics["gross_exposure"] = 50000.0
    _write_artifacts(tmp_path, metrics, decisions, fills)
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
        policy=TradingQualityThresholdPolicy(max_exposure_pct=200.0),
    )
    dim = next(d for d in result["dimensions"] if d["name"] == "exposure_bounds")
    assert not dim["passed"]


def test_turnover_above_threshold_blocks(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    metrics["turnover"] = 150.0
    _write_artifacts(tmp_path, metrics, decisions, fills)
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
        policy=TradingQualityThresholdPolicy(max_turnover=100.0),
    )
    dim = next(d for d in result["dimensions"] if d["name"] == "turnover_bounds")
    assert not dim["passed"]


def test_invalid_nan_metric_blocks(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    metrics["total_return_pct"] = float("nan")
    _write_artifacts(tmp_path, metrics, decisions, fills)
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
    )
    assert result["quality_state"] == "blocked"
    dim = next(d for d in result["dimensions"] if d["name"] == "metric_validity")
    assert not dim["passed"]


def test_valid_gate_reaches_reviewable(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    _write_artifacts(tmp_path, metrics, decisions, fills)
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
    )
    assert result["quality_state"] in ("paper_quality_reviewable", "eligible_for_shadow_live_quality_review")


def test_threshold_policy_serialized(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    _write_artifacts(tmp_path, metrics, decisions, fills)
    policy = TradingQualityThresholdPolicy(min_bars_processed=5)
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
        policy=policy,
    )
    assert result["threshold_policy"]["min_bars_processed"] == 5


def test_artifact_paths_are_redacted(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    _write_artifacts(tmp_path, metrics, decisions, fills)
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
    )
    assert str(tmp_path) not in str(result["input_artifacts"])


def test_benchmark_unavailable_without_data_path(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    _write_artifacts(tmp_path, metrics, decisions, fills)
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
    )
    assert result["benchmark"]["available"] is False


def test_recompute_consistency_succeeds_for_valid_fixtures(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    _write_artifacts(tmp_path, metrics, decisions, fills)
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
    )
    dim = next(d for d in result["dimensions"] if d["name"] == "replay_or_recompute_consistency")
    assert dim["passed"]


def test_artifacts_written(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    _write_artifacts(tmp_path, metrics, decisions, fills)
    report = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
    )
    json_path, md_path = write_trading_quality_artifacts(report, tmp_path / "out")
    assert json_path.exists()
    assert md_path.exists()
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["quality_state"] == report["quality_state"]
    assert "Disclaimer" in md_path.read_text(encoding="utf-8")


def test_symbol_is_ticker_not_data_source(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    metrics["symbol"] = "BTC/USD"
    metrics["data_source_redacted"] = "demo.csv"
    _write_artifacts(tmp_path, metrics, decisions, fills)
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
    )
    assert result["symbol"] == "BTC/USD"
    assert result["metrics"]["data_source_redacted"] == "demo.csv"


def test_symbol_from_state_when_not_in_metrics(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    state = {
        "run_id": metrics["run_id"],
        "symbol": "MSFT",
        "cash": metrics["ending_cash"],
        "equity": metrics["ending_equity"],
        "positions": {},
        "cursor": {"last_processed_bar_index": 9},
    }
    (tmp_path / "state.json").write_text(json.dumps(state), encoding="utf-8")
    _write_artifacts(tmp_path, metrics, decisions, fills)
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
        state_path=tmp_path / "state.json",
    )
    assert result["symbol"] == "MSFT"


def test_symbol_from_fills_fallback(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    metrics.pop("symbol", None)
    for fill in fills:
        fill["symbol"] = "TSLA"
    _write_artifacts(tmp_path, metrics, decisions, fills)
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
    )
    assert result["symbol"] == "TSLA"


def test_missing_symbol_fails_closed(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    metrics.pop("symbol", None)
    for fill in fills:
        fill.pop("symbol", None)
    _write_artifacts(tmp_path, metrics, decisions, fills)
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
    )
    assert result["quality_state"] == "blocked"
    assert any("symbol" in b.lower() for b in result["blockers"])


def test_explicit_symbol_overrides_metrics(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    metrics["symbol"] = "IBM"
    _write_artifacts(tmp_path, metrics, decisions, fills)
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
        symbol="AAPL",
    )
    assert result["symbol"] == "AAPL"


def test_data_source_redacted_is_not_used_as_symbol(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    metrics.pop("symbol", None)
    metrics["data_source_redacted"] = "ohlcv.csv"
    for fill in fills:
        fill.pop("symbol", None)
    _write_artifacts(tmp_path, metrics, decisions, fills)
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
    )
    assert result["symbol"] != "ohlcv.csv"
    assert result["quality_state"] == "blocked"


def test_cli_autonomous_paper_quality_smoke(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    _write_artifacts(tmp_path, metrics, decisions, fills)
    out_dir = tmp_path / "out"
    result = subprocess.run(
        [
            "python3.11", "-m", "atlas_agent.cli",
            "agent", "autonomous-paper-quality",
            "--metrics", str(tmp_path / "metrics.json"),
            "--decisions", str(tmp_path / "decisions.jsonl"),
            "--fills", str(tmp_path / "fills.jsonl"),
            "--output-dir", str(out_dir),
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode in (0, 2), result.stderr
    assert (out_dir / "trading-quality-gate.json").exists()
