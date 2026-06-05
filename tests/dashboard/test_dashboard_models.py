"""Tests for dashboard data layer models."""
from __future__ import annotations

import json

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
    DashboardSystemHealth,
    DashboardStatusSummary,
)


def test_dashboard_snapshot_defaults() -> None:
    s = DashboardSnapshot(
        workspace="/test",
        provider_summary=DashboardStatusSummary(status="unknown"),
    )
    assert s.dashboard_mode == "read_only"
    assert s.mode == "unknown"
    assert s.system_health.available is False
    assert s.portfolio.available is False
    assert s.backtests.available is False
    assert s.reports.available is False
    assert s.reflections.available is False
    assert s.skills.available is False
    assert s.learning.available is False
    assert s.audit.available is False
    assert s.safety.available is False
    assert s.warnings == []
    assert s.missing_data == []


def test_dashboard_snapshot_json_roundtrip() -> None:
    s = DashboardSnapshot(
        workspace="/test",
        mode="paper",
        dashboard_mode="read_only",
        provider_summary=DashboardStatusSummary(status="active"),
        system_health=DashboardSystemHealth(available=True, workspace_initialized=True),
        portfolio=DashboardPortfolio(available=True, cash=1000.0, equity=5000.0),
        backtests=DashboardBacktests(available=True, total_runs=3),
        reports=DashboardReports(available=True, report_count=2),
        reflections=DashboardReflections(available=True, total_count=5),
        skills=DashboardSkills(available=True, candidate_count=2, library_count=1),
        learning=DashboardLearning(available=True, suggestion_count=3),
        audit=DashboardAudit(available=True, recent_events=10),
        safety=DashboardSafety(available=True, kill_switch_mode="normal"),
        warnings=["Test warning"],
        missing_data=["portfolio"],
    )
    data = s.model_dump(mode="json")
    text = json.dumps(data)
    restored = DashboardSnapshot.model_validate_json(text)
    assert restored.workspace == "/test"
    assert restored.mode == "paper"
    assert restored.system_health.workspace_initialized is True
    assert restored.portfolio.cash == 1000.0
    assert restored.backtests.total_runs == 3
    assert restored.warnings == ["Test warning"]
    assert restored.missing_data == ["portfolio"]


def test_dashboard_system_health_checks() -> None:
    sh = DashboardSystemHealth(
        available=True,
        checks=[
            {"id": "workspace.initialized", "status": "pass", "message": "OK"},
        ],
    )
    assert len(sh.checks) == 1
    assert sh.checks[0]["status"] == "pass"


def test_dashboard_safety_fields() -> None:
    sf = DashboardSafety(
        available=True,
        kill_switch_mode="locked_down",
        kill_switch_active=True,
        heartbeat_status="expired",
        live_trading_enabled=False,
        live_submit_enabled=False,
    )
    assert sf.kill_switch_active is True
    assert sf.heartbeat_status == "expired"


def test_dashboard_skills_by_status() -> None:
    sk = DashboardSkills(
        available=True,
        candidate_count=3,
        library_count=1,
        by_status={"draft": 2, "approved": 1},
    )
    assert sk.by_status["draft"] == 2
    assert sk.by_status["approved"] == 1


def test_dashboard_learning_by_status() -> None:
    lr = DashboardLearning(
        available=True,
        suggestion_count=4,
        by_status={"draft": 3, "pending_review": 1},
    )
    assert lr.by_status["draft"] == 3
