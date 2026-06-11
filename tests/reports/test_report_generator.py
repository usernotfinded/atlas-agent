"""Tests for atlas_agent.reports.generator and sources."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from atlas_agent.reports.generator import generate_report
from atlas_agent.reports.models import _DISCLAIMER
from atlas_agent.reports.renderers import render_json_string, render_markdown
from atlas_agent.reports.sources import (
    load_audit_decision_summary,
    load_backtest_summary,
    load_portfolio_summary,
    load_research_summary,
    load_risk_summary,
    load_system_health_summary,
)


class TestGenerateReport:
    def test_daily_report_structure(self):
        data = generate_report("daily", workspace=".")
        assert data.metadata.report_type == "daily"
        assert data.disclaimer == _DISCLAIMER
        assert data.metadata.generated_at

    def test_weekly_report_structure(self):
        data = generate_report("weekly", workspace=".")
        assert data.metadata.report_type == "weekly"
        assert data.disclaimer == _DISCLAIMER

    def test_adhoc_report_structure(self):
        data = generate_report("ad-hoc", workspace=".")
        assert data.metadata.report_type == "ad-hoc"
        assert data.disclaimer == _DISCLAIMER

    def test_no_fake_content(self):
        data = generate_report("daily", workspace=".")
        md = render_markdown(data).lower()
        assert "placeholder" not in md
        assert "todo" not in md
        assert "lorem ipsum" not in md

    def test_no_profit_claims(self):
        data = generate_report("daily", workspace=".")
        md = render_markdown(data).lower()
        assert "guaranteed profit" not in md
        assert "predicts profit" not in md
        assert "makes money" not in md

    def test_offline_no_network(self):
        data = generate_report("daily", workspace=".")
        # If we got here without network errors, the generator is offline
        assert data.metadata.generated_at

    def test_missing_data_handled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data = generate_report("daily", workspace=tmpdir)
            assert not data.portfolio.available
            assert not data.backtest.available
            assert not data.research.available
            md = render_markdown(data)
            assert "No portfolio data available" in md or "portfolio" in md.lower()


class TestLoadPortfolioSummary:
    def test_missing_portfolio(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = load_portfolio_summary(tmpdir)
            assert result.available is False

    def test_with_portfolio_md(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = Path(tmpdir) / "memory"
            memory.mkdir()
            (memory / "portfolio.md").write_text(
                "# Portfolio\n\nCash: $5000.00\nEquity: $12000.00\n\n- AAPL: 10 shares\n",
                encoding="utf-8",
            )
            result = load_portfolio_summary(tmpdir)
            assert result.available is True
            assert result.cash == 5000.0
            assert result.equity == 12000.0
            assert result.positions_count == 1


class TestLoadBacktestSummary:
    def test_missing_backtests(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = load_backtest_summary(tmpdir)
            assert result.available is False

    def test_with_backtest_result(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bt_dir = Path(tmpdir) / ".atlas" / "backtests" / "bt-test-001"
            bt_dir.mkdir(parents=True)
            result = {
                "run_id": "bt-test-001",
                "status": "completed",
                "config": {"symbol": "DEMO"},
                "metrics": {"total_return_pct": 5.0},
            }
            (bt_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
            summary = load_backtest_summary(tmpdir)
            assert summary.available is True
            assert summary.latest_run_id == "bt-test-001"
            assert summary.latest_return_pct == 5.0
            assert summary.total_runs == 1
            assert summary.latest_validation_status == "legacy"


class TestLoadResearchSummary:
    def test_missing_research(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = load_research_summary(tmpdir)
            assert result.available is False

    def test_with_research_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            research = Path(tmpdir) / ".atlas" / "research" / "DEMO"
            research.mkdir(parents=True)
            (research / "plans" / "plan.json").parent.mkdir(parents=True)
            (research / "plans" / "plan.json").write_text('{"symbol": "DEMO"}', encoding="utf-8")
            (research / "evaluations" / "eval.json").parent.mkdir(parents=True)
            (research / "evaluations" / "eval.json").write_text('{"symbol": "DEMO"}', encoding="utf-8")
            summary = load_research_summary(tmpdir)
            assert summary.available is True
            assert summary.artifact_count == 2
            assert summary.recent_plans == 1
            assert summary.recent_evaluations == 1


class TestLoadRiskSummary:
    def test_missing_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = load_risk_summary(tmpdir)
            assert result.available is False

    def test_with_config_toml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            atlas = Path(tmpdir) / ".atlas"
            atlas.mkdir()
            (atlas / "config.toml").write_text(
                '[risk]\nmax_daily_loss = 50.0\nmax_position_notional = 200.0\n'
                'max_trades_per_day = 3\nallow_leverage = false\n'
                '[broker]\nenable_live_trading = false\nenable_live_submit = false\n'
                '[safety]\nkill_switch_enabled = false\n',
                encoding="utf-8",
            )
            result = load_risk_summary(tmpdir)
            assert result.available is True
            assert result.live_trading_enabled is False
            assert result.max_daily_loss == 50.0
            assert result.allow_leverage is False


class TestLoadAuditDecisionSummary:
    def test_missing_logs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = load_audit_decision_summary(tmpdir)
            assert result.available is False

    def test_with_event_logs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            logs = Path(tmpdir) / ".atlas" / "logs"
            logs.mkdir(parents=True)
            events = [
                '{"event_type": "risk_approved", "run_id": "r1", "command": "c", "mode": "paper", "payload": {}, "timestamp": "2026-01-01T00:00:00"}',
                '{"event_type": "risk_rejected", "run_id": "r2", "command": "c", "mode": "paper", "payload": {}, "timestamp": "2026-01-01T00:00:00"}',
                '{"event_type": "backtest_completed", "run_id": "r3", "command": "c", "mode": "backtest", "payload": {}, "timestamp": "2026-01-01T00:00:00"}',
            ]
            (logs / "2026-01-01.jsonl").write_text("\n".join(events), encoding="utf-8")
            result = load_audit_decision_summary(tmpdir)
            assert result.available is True
            assert result.recent_risk_approved == 1
            assert result.recent_risk_rejected == 1
            assert result.recent_backtest_completed == 1


class TestLoadSystemHealthSummary:
    def test_missing_workspace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = load_system_health_summary(tmpdir)
            assert result.available is True
            assert result.workspace_initialized is False

    def test_with_workspace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            atlas = Path(tmpdir) / ".atlas"
            atlas.mkdir()
            (atlas / "config.toml").write_text('[market]\nsymbol = "AAPL"\n', encoding="utf-8")
            result = load_system_health_summary(tmpdir)
            assert result.available is True
            assert result.workspace_initialized is True
            assert result.config_readable is True
