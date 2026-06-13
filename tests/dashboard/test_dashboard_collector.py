"""Tests for dashboard data layer collector."""
from __future__ import annotations

import json
from pathlib import Path

from atlas_agent.config import AtlasConfig
from atlas_agent.dashboard.collectors import collect_dashboard_snapshot


def test_collect_dashboard_snapshot_handles_empty_workspace(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = AtlasConfig(audit_dir=tmp_path / "audit")
    snapshot = collect_dashboard_snapshot(config, tmp_path)

    assert snapshot.workspace == str(tmp_path)
    assert snapshot.configured is True
    assert snapshot.provider_summary.status == "missing"
    assert "OpenAI" in snapshot.provider_summary.message
    assert snapshot.broker_sync_summary.status == "unknown"
    assert snapshot.dashboard_mode == "read_only"
    assert snapshot.system_health.available is True
    assert snapshot.system_health.workspace_initialized is False
    assert snapshot.portfolio.available is False
    assert snapshot.backtests.available is False
    assert snapshot.reports.available is False
    assert snapshot.reflections.available is False
    assert snapshot.skills.available is False
    assert snapshot.learning.available is False
    assert snapshot.audit.available is False
    assert snapshot.safety.available is True
    assert snapshot.missing_data


def test_collect_dashboard_snapshot_with_reflections(tmp_path: Path):
    config = AtlasConfig(audit_dir=tmp_path / "audit")
    reflections_dir = tmp_path / ".atlas" / "reflections"
    reflections_dir.mkdir(parents=True)
    artifact = {
        "reflection_id": "r1",
        "artifact_type": "reflection",
        "status": "draft",
        "provenance": {"input_artifact": {"kind": "report", "path": "test.md"}, "generated_at": "2024-01-01T00:00:00Z"},
        "audit": {"created_at": "2024-01-01T00:00:00Z", "status_transitions": []},
        "output": {"summary": "", "observations": [], "questions": [], "provider_execution_disabled": True, "static_fallback": True},
    }
    (reflections_dir / "r1.json").write_text(json.dumps(artifact), encoding="utf-8")

    snapshot = collect_dashboard_snapshot(config, tmp_path)
    assert snapshot.reflections.available is True
    assert snapshot.reflections.total_count == 1
    assert snapshot.reflections.by_status.get("draft") == 1
    assert "reflections" not in snapshot.missing_data


def test_collect_dashboard_snapshot_with_skills(tmp_path: Path):
    config = AtlasConfig(audit_dir=tmp_path / "audit")
    candidates_dir = tmp_path / ".atlas" / "skill_candidates"
    candidates_dir.mkdir(parents=True)
    candidate = {
        "candidate_id": "c1",
        "artifact_type": "skill_candidate",
        "status": "draft",
        "title": "Test",
        "provenance": {"generator_version": "1.0.0", "generated_at": "2024-01-01T00:00:00Z", "source_kind": "test"},
        "audit": {"created_at": "2024-01-01T00:00:00Z", "status_transitions": []},
    }
    (candidates_dir / "c1.json").write_text(json.dumps(candidate), encoding="utf-8")

    snapshot = collect_dashboard_snapshot(config, tmp_path)
    assert snapshot.skills.available is True
    assert snapshot.skills.candidate_count == 1
    assert snapshot.skills.by_status.get("draft") == 1


def test_collect_dashboard_snapshot_with_learning(tmp_path: Path):
    config = AtlasConfig(audit_dir=tmp_path / "audit")
    suggestions_dir = tmp_path / ".atlas" / "learning" / "suggestions"
    suggestions_dir.mkdir(parents=True)
    suggestion = {
        "suggestion_id": "s1",
        "artifact_type": "learning_suggestion",
        "status": "draft",
        "title": "Test",
        "provenance": {"generator_version": "1.0.0", "generated_at": "2024-01-01T00:00:00Z", "source_kind": "test"},
        "audit": {"created_at": "2024-01-01T00:00:00Z", "status_transitions": []},
    }
    (suggestions_dir / "s1.json").write_text(json.dumps(suggestion), encoding="utf-8")

    snapshot = collect_dashboard_snapshot(config, tmp_path)
    assert snapshot.learning.available is True
    assert snapshot.learning.suggestion_count == 1
    assert snapshot.learning.by_status.get("draft") == 1


def test_collect_dashboard_snapshot_with_backtests(tmp_path: Path):
    config = AtlasConfig(audit_dir=tmp_path / "audit")
    backtests_dir = tmp_path / ".atlas" / "backtests" / "run1"
    backtests_dir.mkdir(parents=True)
    result = {
        "run_id": "run1",
        "status": "completed",
        "config": {"symbol": "AAPL"},
        "metrics": {"total_return_pct": 5.2},
    }
    (backtests_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")

    snapshot = collect_dashboard_snapshot(config, tmp_path)
    assert snapshot.backtests.available is True
    assert snapshot.backtests.total_runs == 1
    assert snapshot.backtests.latest_symbol == "AAPL"
    assert snapshot.backtests.latest_return_pct == 5.2


def test_collect_dashboard_snapshot_with_portfolio(tmp_path: Path):
    config = AtlasConfig(audit_dir=tmp_path / "audit", memory_dir=tmp_path / "memory")
    portfolio_path = tmp_path / "memory" / "portfolio.md"
    portfolio_path.parent.mkdir(parents=True)
    portfolio_path.write_text("# Portfolio\n\nCash: $1,234.56\nEquity: $5,678.90\n- AAPL: 10 shares\n", encoding="utf-8")

    snapshot = collect_dashboard_snapshot(config, tmp_path)
    assert snapshot.portfolio.available is True
    assert snapshot.portfolio.cash == 1234.56
    assert snapshot.portfolio.equity == 5678.90
    assert snapshot.portfolio.positions_count == 1


def test_collect_dashboard_snapshot_no_mutation(tmp_path: Path):
    config = AtlasConfig(audit_dir=tmp_path / "audit")
    snapshot = collect_dashboard_snapshot(config, tmp_path)
    assert snapshot.dashboard_mode == "read_only"
    # Ensure no files were created outside expected dirs
    assert not (tmp_path / ".atlas" / "dashboard" / "index.html").exists()


def test_collect_dashboard_snapshot_safety_status(tmp_path: Path):
    config = AtlasConfig(audit_dir=tmp_path / "audit")
    snapshot = collect_dashboard_snapshot(config, tmp_path)
    assert snapshot.safety.available is True
    assert snapshot.safety.kill_switch_mode == "normal"
    assert snapshot.safety.kill_switch_active is False
    assert snapshot.safety.heartbeat_status in ("unknown", "healthy", "expired")


def test_collect_dashboard_snapshot_warnings_in_live_mode(tmp_path: Path):
    config = AtlasConfig(audit_dir=tmp_path / "audit")
    config.trading_mode = "live"
    snapshot = collect_dashboard_snapshot(config, tmp_path)
    assert any("Live trading" in w for w in snapshot.warnings)


def test_collect_dashboard_snapshot_orders_backtests_by_run_id(tmp_path: Path):
    config = AtlasConfig(audit_dir=tmp_path / "audit")
    backtests_dir = tmp_path / ".atlas" / "backtests"
    runs = [
        ("bt-20260103-120000", "DEMO-SYMBOL", 3.0),
        ("bt-20260101-120000", "AAPL", 1.0),
        ("bt-20260102-120000", "TSLA", 2.0),
    ]
    for run_id, symbol, return_pct in runs:
        run_dir = backtests_dir / run_id
        run_dir.mkdir(parents=True)
        result = {
            "run_id": run_id,
            "status": "completed",
            "config": {"symbol": symbol},
            "metrics": {"total_return_pct": return_pct},
        }
        (run_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")

    snapshot = collect_dashboard_snapshot(config, tmp_path)
    assert snapshot.backtests.available is True
    assert snapshot.backtests.total_runs == 3
    assert snapshot.backtests.latest_run_id == "bt-20260103-120000"
    assert snapshot.backtests.latest_symbol == "DEMO-SYMBOL"
    assert snapshot.backtests.latest_return_pct == 3.0
