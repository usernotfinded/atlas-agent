# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/backtest/test_backtest_reports.py
# PURPOSE: Verifies backtest reports behavior and regression expectations.
# DEPS:    json, tempfile, datetime, pathlib, pytest, atlas_agent.
# ==============================================================================

"""Tests for atlas_agent.backtest.report module."""
# --- IMPORTS ---

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from atlas_agent.backtest.models import (
    BacktestConfig,
    BacktestFill,
    BacktestMetrics,
    BacktestResult,
)
from atlas_agent.backtest.report import (
    _DISCLAIMER,
    render_empty_json_report,
    render_empty_markdown_report,
    render_json_report,
    render_markdown_report,
    write_report_from_result,
)
from atlas_agent.backtest.report_schema import REPORT_SCHEMA_VERSION


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _sample_result() -> BacktestResult:
    """Create a minimal deterministic BacktestResult for testing."""
    return BacktestResult(
        run_id="bt-test-001",
        status="completed",
        config=BacktestConfig(
            run_id="bt-test-001",
            symbol="DEMO-SYMBOL",
            data_path="data/sample/ohlcv.csv",
            initial_equity=10000.0,
            strategy_mode="buy_and_hold",
        ),
        metrics=BacktestMetrics(
            total_return_pct=3.0,
            annualized_return_pct=15.0,
            max_drawdown_pct=1.5,
            trade_count=2,
            win_rate=0.5,
            sharpe_ratio=1.2,
            best_trade_pct=3.0,
            worst_trade_pct=-0.5,
            average_trade_pct=1.25,
            exposure_time_pct=80.0,
            buy_and_hold_return_pct=3.0,
            final_equity=10300.0,
            initial_equity=10000.0,
        ),
        strategy_metadata={
            "strategy_id": "buy_and_hold",
            "name": "Buy and Hold",
            "version": "1.0.0",
        },
        benchmark={
            "benchmark_id": "buy_and_hold",
            "return_pct": 3.0,
        },
        fills=[],
        equity_curve=[
            {"timestamp": "2026-04-20T00:00:00", "equity": 10000.0},
            {"timestamp": "2026-04-25T00:00:00", "equity": 10300.0},
        ],
        diagnostics={},
        started_at=datetime(2026, 4, 20),
        completed_at=datetime(2026, 4, 25),
    )


def _sample_result_with_fills_and_diagnostics() -> BacktestResult:
    """Create a BacktestResult with fills and diagnostics for testing."""
    result = _sample_result()
    result.fills = [
        BacktestFill(
            fill_id="f1",
            order_id="o1",
            timestamp=datetime(2026, 4, 20),
            symbol="DEMO-SYMBOL",
            side="buy",
            quantity=10.0,
            price=100.0,
            notional=1000.0,
            commission=1.0,
            slippage=0.0,
            realized_pnl=0.0,
        ),
        BacktestFill(
            fill_id="f2",
            order_id="o2",
            timestamp=datetime(2026, 4, 21),
            symbol="DEMO-SYMBOL",
            side="sell",
            quantity=10.0,
            price=110.0,
            notional=1100.0,
            commission=1.1,
            slippage=0.0,
            realized_pnl=100.0,
        ),
    ]
    result.diagnostics = {
        "blocked_orders": [
            {"order_id": "o3", "reason": "risk_limit", "violations": []},
        ],
        "strategy_validation": {
            "status": "valid",
            "issues": [],
        },
    }
    return result


# --- JSON report tests ---


class TestRenderJsonReport:
    def test_includes_schema_version(self):
        report = render_json_report(_sample_result())
        assert report["schema_version"] == REPORT_SCHEMA_VERSION

    def test_includes_disclaimer(self):
        report = render_json_report(_sample_result())
        assert report["disclaimer"] == _DISCLAIMER

    def test_includes_report_type(self):
        report = render_json_report(_sample_result())
        assert report["report_type"] == "backtest_research_summary"

    def test_includes_generated_at(self):
        report = render_json_report(_sample_result())
        assert "generated_at" in report

    def test_includes_metrics(self):
        report = render_json_report(_sample_result())
        assert report["metrics"]["total_return_pct"] == 3.0
        assert report["metrics"]["initial_equity"] == 10000.0
        assert report["metrics"]["final_equity"] == 10300.0

    def test_includes_strategy_metadata(self):
        report = render_json_report(_sample_result())
        assert report["strategy_metadata"]["name"] == "Buy and Hold"

    def test_json_serializable(self):
        report = render_json_report(_sample_result())
        serialized = json.dumps(report, default=str)
        assert isinstance(serialized, str)
        parsed = json.loads(serialized)
        assert parsed["run_id"] == "bt-test-001"

    def test_no_fake_content(self):
        report = render_json_report(_sample_result())
        serialized = json.dumps(report, default=str).lower()
        assert "placeholder" not in serialized
        assert "todo" not in serialized
        assert "lorem ipsum" not in serialized

    def test_no_profit_claims(self):
        report = render_json_report(_sample_result())
        serialized = json.dumps(report, default=str).lower()
        assert "guaranteed profit" not in serialized
        assert "predicts profit" not in serialized
        assert "makes money" not in serialized


class TestRenderEmptyJsonReport:
    def test_has_no_data_status(self):
        report = render_empty_json_report()
        assert report["status"] == "no_data"

    def test_has_reason(self):
        report = render_empty_json_report()
        assert report["reason"] == "No backtest data available"

    def test_custom_reason(self):
        report = render_empty_json_report(reason="Missing CSV file")
        assert report["reason"] == "Missing CSV file"

    def test_has_disclaimer(self):
        report = render_empty_json_report()
        assert report["disclaimer"] == _DISCLAIMER


# --- Markdown report tests ---


class TestRenderMarkdownReport:
    def test_includes_symbol(self):
        md = render_markdown_report(_sample_result())
        assert "DEMO-SYMBOL" in md

    def test_includes_strategy_name(self):
        md = render_markdown_report(_sample_result())
        assert "Buy and Hold" in md

    def test_includes_metrics(self):
        md = render_markdown_report(_sample_result())
        assert "Initial Equity" in md
        assert "Final Equity" in md
        assert "Total Return" in md
        assert "Max Drawdown" in md
        assert "Trade Count" in md

    def test_includes_period(self):
        md = render_markdown_report(_sample_result())
        assert "2026-04-20" in md
        assert "2026-04-25" in md

    def test_includes_observations(self):
        md = render_markdown_report(_sample_result())
        assert "Observations" in md

    def test_includes_benchmark(self):
        md = render_markdown_report(_sample_result())
        assert "Benchmark" in md
        assert "buy_and_hold" in md

    def test_includes_disclaimer(self):
        md = render_markdown_report(_sample_result())
        assert "research summary" in md.lower()
        assert "not investment advice" in md.lower()

    def test_no_fake_content(self):
        md = render_markdown_report(_sample_result()).lower()
        assert "placeholder" not in md
        assert "todo" not in md
        assert "lorem ipsum" not in md

    def test_no_profit_claims(self):
        md = render_markdown_report(_sample_result()).lower()
        assert "guaranteed profit" not in md
        assert "predicts profit" not in md

    def test_includes_diagnostics_section(self):
        md = render_markdown_report(_sample_result())
        assert "## Diagnostics" in md
        assert "No diagnostics recorded." in md

    def test_includes_fills_summary_when_no_fills(self):
        md = render_markdown_report(_sample_result())
        assert "## Fills Summary" in md
        assert "No fills recorded." in md

    def test_includes_diagnostics_with_blocked_orders(self):
        md = render_markdown_report(_sample_result_with_fills_and_diagnostics())
        assert "**Blocked Orders:** 1" in md
        assert "**Strategy Validation:** valid" in md

    def test_includes_fills_summary_with_fills(self):
        md = render_markdown_report(_sample_result_with_fills_and_diagnostics())
        assert "**Total Fills:** 2" in md
        assert "**Buy Fills:** 1" in md
        assert "**Sell Fills:** 1" in md
        assert "**Total Notional:** $2,100.00" in md
        assert "**Total Realized PnL:** $100.00" in md
        assert "**Total Commission:** $2.10" in md
        assert "| buy | DEMO-SYMBOL | 10.0000 | $100.00 | $1,000.00 | $0.00 | $1.00 |" in md
        assert "| sell | DEMO-SYMBOL | 10.0000 | $110.00 | $1,100.00 | $100.00 | $1.10 |" in md

    def test_no_fake_content_with_fills(self):
        md = render_markdown_report(_sample_result_with_fills_and_diagnostics()).lower()
        assert "placeholder" not in md
        assert "todo" not in md
        assert "lorem ipsum" not in md

    def test_includes_trade_metrics_with_fills(self):
        md = render_markdown_report(_sample_result_with_fills_and_diagnostics())
        assert "## Trade Metrics" in md
        assert "| Realized Fill Count | 1 |" in md
        assert "| Winning Realized Fills | 1 |" in md
        assert "| Losing Realized Fills | 0 |" in md
        assert "| Best Realized PnL | $100.00 |" in md
        assert "| Worst Realized PnL | $100.00 |" in md
        assert "| Average Realized PnL | $100.00 |" in md
        assert "| Best Trade % | 3.00% |" in md
        assert "| Worst Trade % | -0.50% |" in md
        assert "| Average Trade % | 1.25% |" in md

    def test_includes_trade_metrics_when_no_fills(self):
        md = render_markdown_report(_sample_result())
        assert "## Trade Metrics" in md
        assert "No realized trades recorded." in md
        assert "Best Trade %" not in md
        assert "Worst Trade %" not in md
        assert "Average Trade %" not in md

    def test_trade_metrics_omits_percentage_rows_when_none(self):
        result = _sample_result_with_fills_and_diagnostics()
        result.metrics.best_trade_pct = None
        result.metrics.worst_trade_pct = None
        result.metrics.average_trade_pct = None
        md = render_markdown_report(result)
        assert "## Trade Metrics" in md
        assert "| Realized Fill Count | 1 |" in md
        assert "Best Trade %" not in md
        assert "Worst Trade %" not in md
        assert "Average Trade %" not in md

    def test_trade_metrics_values_with_multiple_sell_fills(self):
        result = _sample_result()
        result.fills = [
            BacktestFill(
                fill_id="f1",
                order_id="o1",
                timestamp=datetime(2026, 4, 20),
                symbol="DEMO-SYMBOL",
                side="sell",
                quantity=10.0,
                price=100.0,
                notional=1000.0,
                commission=1.0,
                slippage=0.0,
                realized_pnl=50.0,
            ),
            BacktestFill(
                fill_id="f2",
                order_id="o2",
                timestamp=datetime(2026, 4, 21),
                symbol="DEMO-SYMBOL",
                side="sell",
                quantity=10.0,
                price=110.0,
                notional=1100.0,
                commission=1.1,
                slippage=0.0,
                realized_pnl=-20.0,
            ),
            BacktestFill(
                fill_id="f3",
                order_id="o3",
                timestamp=datetime(2026, 4, 22),
                symbol="DEMO-SYMBOL",
                side="sell",
                quantity=10.0,
                price=105.0,
                notional=1050.0,
                commission=1.05,
                slippage=0.0,
                realized_pnl=30.0,
            ),
        ]
        md = render_markdown_report(result)
        assert "| Realized Fill Count | 3 |" in md
        assert "| Winning Realized Fills | 2 |" in md
        assert "| Losing Realized Fills | 1 |" in md
        assert "| Best Realized PnL | $50.00 |" in md
        assert "| Worst Realized PnL | $-20.00 |" in md
        assert "| Average Realized PnL | $20.00 |" in md
        assert "| Best Trade % | 3.00% |" in md
        assert "| Worst Trade % | -0.50% |" in md
        assert "| Average Trade % | 1.25% |" in md

    def test_trade_metrics_no_realized_with_only_buy_fills(self):
        result = _sample_result()
        result.fills = [
            BacktestFill(
                fill_id="f1",
                order_id="o1",
                timestamp=datetime(2026, 4, 20),
                symbol="DEMO-SYMBOL",
                side="buy",
                quantity=10.0,
                price=100.0,
                notional=1000.0,
                commission=1.0,
                slippage=0.0,
                realized_pnl=0.0,
            ),
        ]
        md = render_markdown_report(result)
        assert "## Trade Metrics" in md
        assert "No realized trades recorded." in md
        assert "Best Trade %" not in md
        assert "Worst Trade %" not in md
        assert "Average Trade %" not in md


class TestRenderMarkdownReportDiagnostics:
    def test_empty_diagnostics_renders_clear_fallback(self):
        result = _sample_result()
        result.diagnostics = {}
        md = render_markdown_report(result)
        assert "## Diagnostics" in md
        assert "No diagnostics recorded." in md

    def test_redacted_diagnostics_renders_explicit_text(self):
        result = _sample_result()
        result.diagnostics = {"redacted": True}
        md = render_markdown_report(result)
        assert "## Diagnostics" in md
        assert "Diagnostics redacted." in md
        assert "Blocked Orders" not in md

    def test_sensitive_diagnostics_are_scrubbed_in_markdown(self):
        result = _sample_result_with_fills_and_diagnostics()
        result.diagnostics["api_key"] = "super-secret-key"
        result.diagnostics["nested"] = {"password": "hunter2"}
        md = render_markdown_report(result)
        assert "super-secret-key" not in md
        assert "hunter2" not in md
        assert "[redacted]" in md
        assert "**Blocked Orders:** 1" in md

    def test_sensitive_diagnostics_are_scrubbed_in_json(self):
        result = _sample_result_with_fills_and_diagnostics()
        result.diagnostics["api_key"] = "super-secret-key"
        result.diagnostics["tokens"] = ["abc", "def"]
        report = render_json_report(result)
        assert report["diagnostics"]["api_key"] == "[redacted]"
        assert report["diagnostics"]["tokens"] == "[redacted]"
        assert "super-secret-key" not in json.dumps(report)


class TestRenderEmptyMarkdownReport:
    def test_contains_no_data_message(self):
        md = render_empty_markdown_report()
        assert "No backtest data available" in md

    def test_contains_disclaimer(self):
        md = render_empty_markdown_report()
        assert "research summary" in md.lower()

    def test_custom_reason(self):
        md = render_empty_markdown_report(reason="CSV not found")
        assert "CSV not found" in md


# --- write_report_from_result tests ---


class TestWriteReportFromResult:
    def test_writes_json_and_md(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path, md_path = write_report_from_result(
                _sample_result(), output_dir=tmpdir
            )
            assert json_path.exists()
            assert md_path.exists()

    def test_json_file_is_valid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path, _ = write_report_from_result(
                _sample_result(), output_dir=tmpdir
            )
            data = json.loads(json_path.read_text(encoding="utf-8"))
            assert data["disclaimer"] == _DISCLAIMER
            assert data["run_id"] == "bt-test-001"

    def test_md_file_has_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _, md_path = write_report_from_result(
                _sample_result(), output_dir=tmpdir
            )
            content = md_path.read_text(encoding="utf-8")
            assert "DEMO-SYMBOL" in content
            assert "Backtest Research Summary" in content

    def test_creates_nested_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = Path(tmpdir) / "a" / "b" / "c"
            json_path, md_path = write_report_from_result(
                _sample_result(), output_dir=nested
            )
            assert json_path.exists()
            assert md_path.exists()
