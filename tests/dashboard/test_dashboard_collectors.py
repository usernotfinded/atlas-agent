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


def test_collect_dashboard_snapshot_redacts_diagnostics(tmp_path: Path):
    config = AtlasConfig()
    snapshot = collect_dashboard_snapshot(config, tmp_path)
    
    assert snapshot.diagnostics.get("redacted") is True


def test_dashboard_provider_summary_uses_config_not_ai_provider_env(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    config = AtlasConfig()
    config.model.provider = "openrouter"

    snapshot = collect_dashboard_snapshot(config, tmp_path)

    assert snapshot.provider_summary.status == "missing"
    assert "OpenRouter" in snapshot.provider_summary.message
    assert "openrouter" in snapshot.provider_summary.message
    assert "anthropic" not in snapshot.provider_summary.message.lower()


def test_dashboard_provider_summary_handles_unknown_provider(tmp_path: Path):
    config = AtlasConfig()
    config.model.provider = "unknown-provider"

    snapshot = collect_dashboard_snapshot(config, tmp_path)

    assert snapshot.provider_summary.status == "unknown"
    assert "unknown-provider" in snapshot.provider_summary.message
