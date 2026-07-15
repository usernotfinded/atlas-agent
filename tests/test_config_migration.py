# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_config_migration.py
# PURPOSE: Verifies config migration behavior and regression expectations.
# DEPS:    json, pytest, pathlib, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

import json
import pytest
from pathlib import Path
from atlas_agent.config.migrate import migrate_legacy_config
from atlas_agent.config.paths import get_config_toml_path, get_env_atlas_path, get_legacy_config_json_path
from atlas_agent.config import get_config

# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("TRADING_MODE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

def test_migration_from_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    
    # Create legacy config
    dot_atlas = tmp_path / ".atlas"
    dot_atlas.mkdir()
    legacy_json = dot_atlas / "config.json"
    legacy_json.write_text(json.dumps({
        "provider": "anthropic",
        "model": "claude-3",
        "OPENROUTER_API_KEY": "sk-test",
        "trust_mode": "live"
    }))
    
    # Run migration
    assert migrate_legacy_config() == True
    
    # Check TOML
    config = get_config()
    assert config.model.provider == "anthropic"
    assert config.model.model == "claude-3"
    assert config.trading_mode == "live"
    
    # Check secrets
    env_atlas = get_env_atlas_path()
    assert env_atlas.exists()
    content = env_atlas.read_text()
    assert "OPENROUTER_API_KEY=" in content
    assert "sk-test" in content
    
    # Original should still exist (it's a backup)
    assert legacy_json.exists()
