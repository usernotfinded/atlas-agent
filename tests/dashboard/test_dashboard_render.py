from __future__ import annotations

import json
from pathlib import Path
from atlas_agent.dashboard.models import DashboardSnapshot, DashboardStatusSummary
from atlas_agent.dashboard.render import render_dashboard_html, render_dashboard_markdown


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
    assert "System Status" in content
    assert "Kill Switch" in content
    assert "Broker Sync" in content
    assert "Audit Health" in content
    assert "Risk Manager" in content
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
