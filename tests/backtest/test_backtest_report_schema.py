# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/backtest/test_backtest_report_schema.py
# PURPOSE: Verifies backtest report schema behavior and regression expectations.
# DEPS:    json, datetime, pytest, atlas_agent.
# ==============================================================================

"""Tests for backtest report schema contract (CAND-003)."""
# --- IMPORTS ---

from __future__ import annotations

import json
from datetime import datetime

import pytest

from atlas_agent.backtest.models import (
    BacktestConfig,
    BacktestFill,
    BacktestMetrics,
    BacktestResult,
)
from atlas_agent.backtest.report import render_json_report
from atlas_agent.backtest.report_schema import (
    REPORT_SCHEMA_VERSION,
    ReportSchemaError,
    collect_backtest_report_schema_errors,
    get_schema_validation_result,
    unreadable_schema_result,
    validate_backtest_report,
    validate_backtest_result,
)


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _sample_result() -> BacktestResult:
    return BacktestResult(
        run_id="bt-schema-001",
        status="completed",
        config=BacktestConfig(
            run_id="bt-schema-001",
            symbol="DEMO-SYMBOL",
            data_path="data/sample/ohlcv.csv",
            initial_equity=10000.0,
            strategy_mode="buy_and_hold",
        ),
        metrics=BacktestMetrics(
            total_return_pct=3.0,
            max_drawdown_pct=1.5,
            trade_count=2,
            final_equity=10300.0,
            initial_equity=10000.0,
        ),
        strategy_metadata={"strategy_id": "buy_and_hold", "name": "Buy and Hold"},
        benchmark={},
        fills=[],
        equity_curve=[
            {"timestamp": "2026-04-20T00:00:00", "equity": 10000.0},
        ],
        diagnostics={"blocked_orders": []},
        started_at=datetime(2026, 4, 20),
        completed_at=datetime(2026, 4, 25),
    )


def test_valid_report_passes():
    report = render_json_report(_sample_result())
    validate_backtest_report(report)


def test_validate_backtest_result_wrapper():
    report = validate_backtest_result(_sample_result())
    assert report["schema_version"] == REPORT_SCHEMA_VERSION


def test_missing_schema_version_fails():
    report = render_json_report(_sample_result())
    del report["schema_version"]
    with pytest.raises(ReportSchemaError, match="Missing top-level keys"):
        validate_backtest_report(report)


def test_wrong_schema_version_fails():
    report = render_json_report(_sample_result())
    report["schema_version"] = "backtest.report.v0"
    with pytest.raises(ReportSchemaError, match="Unexpected schema_version"):
        validate_backtest_report(report)


def test_missing_required_metric_fails():
    report = render_json_report(_sample_result())
    del report["metrics"]["total_return_pct"]
    with pytest.raises(ReportSchemaError, match="Missing metric keys"):
        validate_backtest_report(report)


def test_missing_config_key_fails():
    report = render_json_report(_sample_result())
    del report["config"]["symbol"]
    with pytest.raises(ReportSchemaError, match="Missing config keys"):
        validate_backtest_report(report)


def test_invalid_fill_side_fails():
    report = render_json_report(_sample_result())
    report["fills"] = [
        {
            "side": "invalid",
            "symbol": "AAPL",
            "quantity": 1.0,
            "price": 100.0,
            "notional": 100.0,
        }
    ]
    with pytest.raises(ReportSchemaError, match=r"fills\[0\]\.side must be"):
        validate_backtest_report(report)


def test_missing_equity_curve_key_fails():
    report = render_json_report(_sample_result())
    report["equity_curve"] = [{"timestamp": "2026-01-01T00:00:00"}]
    with pytest.raises(ReportSchemaError, match=r"equity_curve\[0\] missing"):
        validate_backtest_report(report)


def test_non_dict_report_fails():
    with pytest.raises(ReportSchemaError, match="must be a JSON object"):
        validate_backtest_report("not a dict")


def test_fill_with_realized_pnl_passes():
    report = render_json_report(_sample_result())
    report["fills"] = [
        {
            "side": "sell",
            "symbol": "AAPL",
            "quantity": 10.0,
            "price": 110.0,
            "notional": 1100.0,
            "realized_pnl": 100.0,
        }
    ]
    validate_backtest_report(report)


# --- collect_backtest_report_schema_errors tests ---


def test_collect_errors_empty_for_valid_report():
    report = render_json_report(_sample_result())
    errs = collect_backtest_report_schema_errors(report)
    assert errs == []


def test_collect_errors_multiple_missing_top_level_keys():
    report = render_json_report(_sample_result())
    del report["schema_version"]
    del report["run_id"]
    del report["metrics"]
    errs = collect_backtest_report_schema_errors(report)
    assert len(errs) >= 1
    assert any("Missing top-level keys" in e for e in errs)
    # Should list all three missing keys in a single error
    top_err = [e for e in errs if "Missing top-level keys" in e][0]
    assert "metrics" in top_err
    assert "run_id" in top_err
    assert "schema_version" in top_err


def test_collect_errors_multiple_missing_metric_keys():
    report = render_json_report(_sample_result())
    del report["metrics"]["total_return_pct"]
    del report["metrics"]["trade_count"]
    errs = collect_backtest_report_schema_errors(report)
    assert any("Missing metric keys" in e for e in errs)
    metric_err = [e for e in errs if "Missing metric keys" in e][0]
    assert "total_return_pct" in metric_err
    assert "trade_count" in metric_err


def test_collect_errors_cross_category():
    report = render_json_report(_sample_result())
    del report["schema_version"]
    del report["metrics"]["total_return_pct"]
    del report["config"]["symbol"]
    errs = collect_backtest_report_schema_errors(report)
    assert any("Missing top-level keys" in e for e in errs)
    assert any("Missing metric keys" in e for e in errs)
    assert any("Missing config keys" in e for e in errs)


def test_collect_errors_multiple_fill_problems():
    report = render_json_report(_sample_result())
    report["fills"] = [
        {"side": "invalid", "symbol": "A", "quantity": 1.0, "price": 1.0, "notional": 1.0},
        {"side": "buy", "symbol": "B", "quantity": 1.0},
    ]
    errs = collect_backtest_report_schema_errors(report)
    assert any("fills[0].side must be" in e for e in errs)
    assert any("fills[1] missing key: price" in e for e in errs)
    assert any("fills[1] missing key: notional" in e for e in errs)


def test_invalid_report_has_errors_list():
    report = render_json_report(_sample_result())
    del report["metrics"]["total_return_pct"]
    del report["config"]["symbol"]
    result = get_schema_validation_result(report)
    assert result.errors is not None
    assert len(result.errors) >= 2
    assert any("Missing metric keys" in e for e in result.errors)
    assert any("Missing config keys" in e for e in result.errors)


def test_date_filtering_metadata_present():
    result = _sample_result()
    result.config.start_date = "2026-04-01"
    result.config.end_date = "2026-04-30"
    report = render_json_report(result)
    validate_backtest_report(report)
    assert report["config"]["start_date"] == "2026-04-01"
    assert report["config"]["end_date"] == "2026-04-30"


# --- get_schema_validation_result tests ---


class TestGetSchemaValidationResult:
    def test_valid_report(self):
        report = render_json_report(_sample_result())
        result = get_schema_validation_result(report)
        assert result.status == "valid"
        assert result.valid is True
        assert result.error is None
        assert result.schema_version == REPORT_SCHEMA_VERSION

    def test_legacy_report(self):
        report = render_json_report(_sample_result())
        del report["schema_version"]
        result = get_schema_validation_result(report)
        assert result.status == "legacy"
        assert result.valid is False
        assert result.error is None
        assert result.schema_version is None

    def test_invalid_report(self):
        report = render_json_report(_sample_result())
        del report["metrics"]["total_return_pct"]
        result = get_schema_validation_result(report)
        assert result.status.startswith("invalid:")
        assert result.valid is False
        assert result.error is not None
        assert "Missing metric keys" in result.error
        assert result.schema_version == REPORT_SCHEMA_VERSION

    def test_unreadable_report(self):
        result = get_schema_validation_result("not a dict")
        assert result.status == "unreadable"
        assert result.valid is False
        assert result.error == "unreadable"
        assert result.schema_version is None

    def test_invalid_status(self):
        report = render_json_report(_sample_result())
        report["status"] = "unknown"
        result = get_schema_validation_result(report)
        assert result.valid is False
        assert "Unexpected status" in result.error

    def test_unreadable_schema_result_helper(self):
        result = unreadable_schema_result("unreadable: bad json")
        assert result.status == "unreadable"
        assert result.valid is False
        assert result.error == "unreadable: bad json"
        assert result.errors == ["unreadable: bad json"]
        assert result.schema_version is None
