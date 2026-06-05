"""Tests for atlas_agent.reports.renderers."""
from __future__ import annotations

import json

import pytest

from atlas_agent.reports.models import (
    AuditDecisionSummary,
    BacktestSummary,
    MissingDataSection,
    PortfolioSummary,
    ReportData,
    ReportMetadata,
    ResearchSummary,
    RiskSummary,
    SystemHealthSummary,
    _DISCLAIMER,
)
from atlas_agent.reports.renderers import render_json, render_json_string, render_markdown


def _sample_report() -> ReportData:
    return ReportData(
        metadata=ReportMetadata(
            report_type="daily",
            generated_at="2026-06-05T10:00:00",
            format="markdown",
            version="1.0.0",
            workspace=".",
        ),
        portfolio=PortfolioSummary(
            available=True,
            cash=5000.0,
            equity=12000.0,
            positions_count=1,
            positions=[{"line": "- AAPL: 10 shares"}],
            symbol="AAPL",
        ),
        backtest=BacktestSummary(
            available=True,
            recent_count=3,
            latest_run_id="bt-001",
            latest_symbol="DEMO",
            latest_return_pct=5.0,
            latest_status="completed",
            total_runs=10,
        ),
        research=ResearchSummary(
            available=True,
            artifact_count=5,
            recent_evaluations=2,
            recent_plans=1,
            recent_verifications=1,
            symbol="DEMO",
        ),
        risk=RiskSummary(
            available=True,
            live_trading_enabled=False,
            live_submit_enabled=False,
            kill_switch_enabled=False,
            max_daily_loss=100.0,
            max_position_notional=1000.0,
            max_trades_per_day=5,
            allow_leverage=False,
        ),
        audit_decisions=AuditDecisionSummary(
            available=True,
            recent_events=20,
            recent_risk_approved=3,
            recent_risk_rejected=1,
            recent_backtest_completed=4,
            recent_backtest_failed=0,
        ),
        system_health=SystemHealthSummary(
            available=True,
            workspace_initialized=True,
            config_readable=True,
            ready_for_backtesting=True,
            ready_for_paper_agentic=False,
            ready_for_live=False,
            checks=[{"id": "workspace.initialized", "status": "pass", "message": "OK"}],
        ),
        missing_data=MissingDataSection(missing_sources=[]),
        disclaimer=_DISCLAIMER,
    )


class TestRenderMarkdown:
    def test_includes_metadata(self):
        md = render_markdown(_sample_report())
        assert "Atlas Agent Report: Daily" in md
        assert "2026-06-05T10:00:00" in md

    def test_includes_portfolio(self):
        md = render_markdown(_sample_report())
        assert "Portfolio Summary" in md
        assert "5000.0000" in md or "5000" in md

    def test_includes_backtest(self):
        md = render_markdown(_sample_report())
        assert "Backtest Summary" in md
        assert "bt-001" in md

    def test_includes_research(self):
        md = render_markdown(_sample_report())
        assert "Research Summary" in md
        assert "5" in md

    def test_includes_risk(self):
        md = render_markdown(_sample_report())
        assert "Risk Summary" in md
        assert "Live Trading" in md

    def test_includes_audit(self):
        md = render_markdown(_sample_report())
        assert "Audit / Decision Summary" in md
        assert "20" in md

    def test_includes_system_health(self):
        md = render_markdown(_sample_report())
        assert "System Health Summary" in md
        assert "Workspace Initialized" in md

    def test_includes_disclaimer(self):
        md = render_markdown(_sample_report())
        assert "not investment advice" in md.lower()

    def test_no_fake_content(self):
        md = render_markdown(_sample_report()).lower()
        assert "placeholder" not in md
        assert "todo" not in md

    def test_missing_data_section(self):
        report = _sample_report()
        report.missing_data = MissingDataSection(missing_sources=["portfolio", "backtest"])
        md = render_markdown(report)
        assert "Missing Data" in md
        assert "portfolio" in md
        assert "backtest" in md

    def test_missing_data_hidden_when_empty(self):
        md = render_markdown(_sample_report())
        assert "Missing Data" not in md

    def test_unavailable_sections(self):
        report = _sample_report()
        report.portfolio = PortfolioSummary(available=False)
        md = render_markdown(report)
        assert "No portfolio data available" in md


class TestRenderJson:
    def test_includes_metadata(self):
        payload = render_json(_sample_report())
        assert payload["metadata"]["report_type"] == "daily"
        assert payload["metadata"]["generated_at"] == "2026-06-05T10:00:00"

    def test_includes_all_sections(self):
        payload = render_json(_sample_report())
        assert payload["portfolio"]["available"] is True
        assert payload["backtest"]["latest_run_id"] == "bt-001"
        assert payload["research"]["artifact_count"] == 5
        assert payload["risk"]["live_trading_enabled"] is False
        assert payload["audit_decisions"]["recent_events"] == 20
        assert payload["system_health"]["workspace_initialized"] is True

    def test_includes_disclaimer(self):
        payload = render_json(_sample_report())
        assert "not investment advice" in payload["disclaimer"].lower()

    def test_json_serializable(self):
        payload = render_json_string(_sample_report())
        parsed = json.loads(payload)
        assert parsed["metadata"]["report_type"] == "daily"

    def test_missing_data_as_list(self):
        report = _sample_report()
        report.missing_data = MissingDataSection(missing_sources=["portfolio"])
        payload = render_json(report)
        assert payload["missing_data"] == ["portfolio"]
