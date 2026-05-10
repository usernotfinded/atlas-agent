import os
import pytest
from pathlib import Path
from atlas_agent.config import AtlasConfig, get_config, update_config_value, delete_config_value, set_atlas_secret
from atlas_agent.config.paths import get_config_toml_path, get_env_atlas_path

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("TRADING_MODE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

def test_config_load_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(exist_ok=True)
    # Ensure no config exists
    config = get_config()
    assert config.trading_mode == "paper"
    assert config.model.provider == "openai"

def test_config_set_non_secret(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(exist_ok=True)
    update_config_value("trading_mode", "live")
    
    config = get_config()
    assert config.trading_mode == "live"
    
    toml_path = get_config_toml_path()
    assert toml_path.exists()
    content = toml_path.read_text()
    assert 'trading_mode = "live"' in content

def test_config_set_secret_routing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(exist_ok=True)
    update_config_value("openai_api_key", "test-key")
    
    # Should NOT be in config.toml
    config_toml = get_config_toml_path()
    if config_toml.exists():
        assert "test-key" not in config_toml.read_text()
        
    # Should BE in .env.atlas
    env_atlas = get_env_atlas_path()
    assert env_atlas.exists()
    content = env_atlas.read_text()
    assert "OPENAI_API_KEY=" in content
    assert "test-key" in content

def test_nested_config_set(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(exist_ok=True)
    update_config_value("model.model", "gpt-5")
    
    config = get_config()
    assert config.model.model == "gpt-5"
    
    toml_path = get_config_toml_path()
    assert "[model]" in toml_path.read_text()
    assert 'model = "gpt-5"' in toml_path.read_text()

def test_config_compatibility_properties(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(exist_ok=True)
    update_config_value("broker.provider", "alpaca")
    update_config_value("broker.enable_live_trading", True)
    
    config = get_config()
    assert config.live_broker == "alpaca"
    assert config.enable_live_trading == True

def test_redaction(tmp_path, monkeypatch):
    from atlas_agent.config import redact_value
    assert redact_value("1234567890") == "1234...7890"
    assert redact_value("short") == "*****"
