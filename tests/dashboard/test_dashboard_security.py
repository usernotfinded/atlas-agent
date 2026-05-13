from __future__ import annotations

import os
from pathlib import Path
from atlas_agent.config import AtlasConfig
from atlas_agent.dashboard.collectors import collect_dashboard_snapshot


def test_collect_dashboard_snapshot_redacts_environment_variables(tmp_path: Path, monkeypatch):
    # Set sensitive environment variables
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-123")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret-alpaca-key")
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    
    config = AtlasConfig()
    config.model.provider = "anthropic"
    snapshot = collect_dashboard_snapshot(config, tmp_path)
    
    # Check that they are not in the message
    assert "sk-ant-123" not in snapshot.provider_summary.message
    assert "anthropic" in snapshot.provider_summary.message.lower()
    assert "credentials configured" in snapshot.provider_summary.message.lower()

    # If we added diagnostics collection for env vars in the future, 
    # we must ensure they are redacted.


def test_ai_provider_env_does_not_override_dashboard_config(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-123")

    config = AtlasConfig()
    config.model.provider = "openai"
    snapshot = collect_dashboard_snapshot(config, tmp_path)

    assert "OpenAI" in snapshot.provider_summary.message
    assert "anthropic" not in snapshot.provider_summary.message.lower()
    assert "sk-ant-123" not in snapshot.provider_summary.message
