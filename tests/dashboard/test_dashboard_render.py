from __future__ import annotations

import json
from pathlib import Path
from atlas_agent.dashboard.models import (
    DashboardAudit,
    DashboardBacktests,
    DashboardLearning,
    DashboardPortfolio,
    DashboardReflections,
    DashboardReports,
    DashboardSafety,
    DashboardSkills,
    DashboardSnapshot,
    DashboardStatusSummary,
    DashboardSystemHealth,
)
from atlas_agent.dashboard.render import render_dashboard_html, render_dashboard_markdown


def _full_snapshot() -> DashboardSnapshot:
    return DashboardSnapshot(
        workspace="/test",
        mode="paper",
        dashboard_mode="read_only",
        provider_summary=DashboardStatusSummary(status="active", message="Provider: test; credentials not required"),
        broker_sync_summary=DashboardStatusSummary(status="success"),
        risk_summary=DashboardStatusSummary(status="enabled"),
        heartbeat_summary=DashboardStatusSummary(status="healthy", last_updated="2026-01-01T00:00:00Z"),
        diagnostics={"safe_key": "safe-value"},
        system_health=DashboardSystemHealth(
            available=True,
            workspace_initialized=True,
            config_readable=True,
            ready_for_backtesting=True,
            ready_for_paper_agentic=True,
            ready_for_live="Missing live trading config",
            checks=[{"id": "workspace.initialized", "status": "pass", "message": "Workspace has config"}],
        ),
        portfolio=DashboardPortfolio(available=True, cash=1000.0, equity=1200.0, positions_count=2, symbol="AAPL"),
        backtests=DashboardBacktests(
            available=True,
            total_runs=3,
            recent_count=2,
            latest_run_id="run-1",
            latest_symbol="AAPL",
            latest_return_pct=1.5,
            latest_status="completed",
            latest_schema_version="backtest.report.v1",
            latest_validation_status="valid",
        ),
        reports=DashboardReports(available=True, report_count=2, latest_report_type="markdown", latest_generated_at="2026-01-01T00:00:00Z"),
        reflections=DashboardReflections(available=True, total_count=2, by_status={"draft": 1, "approved": 1}),
        skills=DashboardSkills(available=True, candidate_count=1, library_count=1, by_status={"draft": 1}),
        learning=DashboardLearning(available=True, suggestion_count=1, by_status={"draft": 1}),
        audit=DashboardAudit(available=True, recent_events=5, recent_risk_approved=1, recent_risk_rejected=1, recent_backtest_completed=2),
        safety=DashboardSafety(available=True, kill_switch_mode="normal", heartbeat_status="healthy"),
        warnings=["Review live-mode configuration before use"],
        missing_data=["audit_events"],
    )


def test_render_dashboard_html_includes_required_dashboard_sections(tmp_path: Path):
    snapshot = _full_snapshot()
    output_path = tmp_path / "dashboard.html"
    render_dashboard_html(snapshot, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert "Atlas Agent Dashboard" in content
    assert "Generated:" in content
    assert "Workspace:" in content
    assert "dashboard: read_only" in content
    assert "local" in content
    assert "paper_or_sandbox" in content
    assert "Safety status:" in content
    assert "System Health" in content
    assert "Portfolio Summary" in content
    assert "Backtest Summary" in content
    assert "Latest schema version" in content
    assert "Latest validation status" in content
    assert "Report Summary" in content
    assert "Reflection Summary" in content
    assert "Skills Summary" in content
    assert "Learning Summary" in content
    assert "Audit / Event Summary" in content
    assert "Missing Data" in content
    assert "Warnings" in content
    assert "Recent Diagnostics" in content


def test_render_dashboard_html_includes_required_safety_copy(tmp_path: Path):
    snapshot = _full_snapshot()
    output_path = tmp_path / "dashboard.html"
    render_dashboard_html(snapshot, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert "This dashboard is read-only." in content
    assert "This dashboard does not execute trades." in content
    assert "This dashboard does not call providers or brokers." in content
    assert "This dashboard is not financial advice." in content


def test_render_dashboard_html_includes_core_cards(tmp_path: Path):
    snapshot = DashboardSnapshot(
        workspace="/test",
        provider_summary=DashboardStatusSummary(status="active"),
        broker_sync_summary=DashboardStatusSummary(status="success"),
        risk_summary=DashboardStatusSummary(status="enabled"),
        heartbeat_summary=DashboardStatusSummary(status="healthy")
    )
    
    output_path = tmp_path / "dashboard.html"
    render_dashboard_html(snapshot, output_path)
    
    content = output_path.read_text(encoding="utf-8")
    assert "System Health" in content
    assert "Safety Status" in content
    assert "Broker Sync" in content
    assert "Audit / Event Summary" in content
    assert "Recent Diagnostics" in content


def test_render_dashboard_html_displays_provided_diagnostics(tmp_path: Path):
    snapshot = DashboardSnapshot(
        workspace="/test",
        provider_summary=DashboardStatusSummary(status="active"),
        broker_sync_summary=DashboardStatusSummary(status="success"),
        risk_summary=DashboardStatusSummary(status="enabled"),
        heartbeat_summary=DashboardStatusSummary(status="healthy"),
        diagnostics={"safe_key": "safe-value"}
    )
    
    output_path = tmp_path / "dashboard.html"
    render_dashboard_html(snapshot, output_path)
    content = output_path.read_text(encoding="utf-8")
    
    assert "safe-value" in content


def test_render_dashboard_html_empty_states_are_explicit(tmp_path: Path):
    snapshot = DashboardSnapshot(workspace="/test")
    output_path = tmp_path / "dashboard.html"
    render_dashboard_html(snapshot, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert "No data available" in content
    assert "Missing Data" in content
    assert "Warnings" in content


def test_render_dashboard_html_has_no_mutating_controls_or_external_assets(tmp_path: Path):
    snapshot = _full_snapshot()
    output_path = tmp_path / "dashboard.html"
    render_dashboard_html(snapshot, output_path)

    content = output_path.read_text(encoding="utf-8").lower()
    assert "<form" not in content
    assert "<button" not in content
    assert "<input" not in content
    assert "<select" not in content
    assert "<textarea" not in content
    assert "<script" not in content
    assert "cdn." not in content
    assert "http://" not in content
    assert "https://" not in content
    assert "submit order" not in content
    assert "enable live trading" not in content
    assert "enable provider execution" not in content
    assert "enable broker execution" not in content
    assert "activate skill" not in content
    assert "run learning" not in content


def test_render_dashboard_html_escapes_snapshot_values(tmp_path: Path):
    snapshot = DashboardSnapshot(
        workspace="<unsafe>",
        diagnostics={"safe_key": "<unsafe-value>"},
        warnings=["<unsafe-warning>"],
    )
    output_path = tmp_path / "dashboard.html"
    render_dashboard_html(snapshot, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert "&lt;unsafe&gt;" in content
    assert "&lt;unsafe-value&gt;" in content
    assert "&lt;unsafe-warning&gt;" in content
    assert "<unsafe>" not in content
    assert "<unsafe-value>" not in content
    assert "<unsafe-warning>" not in content


def test_render_dashboard_html_only_writes_requested_output_path(tmp_path: Path):
    snapshot = _full_snapshot()
    output_path = tmp_path / "nested" / "dashboard.html"
    render_dashboard_html(snapshot, output_path)

    assert output_path.exists()
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == [
        Path("nested"),
        Path("nested/dashboard.html"),
    ]


def test_render_dashboard_markdown_contains_sections():
    snapshot = DashboardSnapshot(
        workspace="/test",
        provider_summary=DashboardStatusSummary(status="active"),
        broker_sync_summary=DashboardStatusSummary(status="success"),
        risk_summary=DashboardStatusSummary(status="enabled"),
        heartbeat_summary=DashboardStatusSummary(status="healthy"),
    )
    md = render_dashboard_markdown(snapshot)
    assert "# Atlas Agent Dashboard" in md
    assert "## System Health" in md
    assert "## Portfolio" in md
    assert "## Backtests" in md
    assert "Latest Schema Version" in md
    assert "Latest Validation Status" in md
    assert "## Reports" in md
    assert "## Reflections" in md
    assert "## Skills" in md
    assert "## Learning Suggestions" in md
    assert "## Audit" in md
    assert "## Safety" in md
    assert "read-only" in md.lower()


def test_render_dashboard_markdown_with_warnings():
    snapshot = DashboardSnapshot(
        workspace="/test",
        provider_summary=DashboardStatusSummary(status="active"),
        broker_sync_summary=DashboardStatusSummary(status="success"),
        risk_summary=DashboardStatusSummary(status="enabled"),
        heartbeat_summary=DashboardStatusSummary(status="healthy"),
        warnings=["Test warning"],
    )
    md = render_dashboard_markdown(snapshot)
    assert "## Warnings" in md
    assert "Test warning" in md


def test_render_dashboard_markdown_with_missing_data():
    snapshot = DashboardSnapshot(
        workspace="/test",
        provider_summary=DashboardStatusSummary(status="active"),
        broker_sync_summary=DashboardStatusSummary(status="success"),
        risk_summary=DashboardStatusSummary(status="enabled"),
        heartbeat_summary=DashboardStatusSummary(status="healthy"),
        missing_data=["portfolio", "backtest"],
    )
    md = render_dashboard_markdown(snapshot)
    assert "## Missing Data" in md
    assert "portfolio" in md
    assert "backtest" in md
