from __future__ import annotations

import json
from pathlib import Path
from atlas_agent.dashboard.models import DashboardSnapshot, DashboardStatusSummary
from atlas_agent.dashboard.render import render_dashboard_html


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
