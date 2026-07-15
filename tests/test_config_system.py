# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_config_system.py
# PURPOSE: Verifies config system behavior and regression expectations.
# DEPS:    os, pytest, pathlib, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

import os
import pytest
from pathlib import Path
from atlas_agent.config import AtlasConfig, get_config, set_raw_value, unset_raw_value, set_secret
from atlas_agent.config.paths import get_config_toml_path, get_env_atlas_path
from atlas_agent.config.secrets import InvalidSecretValueError, load_atlas_secrets

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
    set_raw_value("trading_mode", "live")
    
    config = get_config()
    assert config.trading_mode == "live"
    
    toml_path = get_config_toml_path()
    assert toml_path.exists()
    content = toml_path.read_text()
    assert 'trading_mode = "live"' in content

def test_config_set_secret_routing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(exist_ok=True)
    set_secret("OPENAI_API_KEY", "test-key")
    
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

def test_set_secret_single_line_value_reloads(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(exist_ok=True)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    set_secret("OPENAI_API_KEY", "single-line-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    load_atlas_secrets()

    assert os.environ["OPENAI_API_KEY"] == "single-line-key"
    config_toml = get_config_toml_path()
    if config_toml.exists():
        assert "single-line-key" not in config_toml.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "secret_value",
    [
        "bad\nINJECTED_SECRET=leak",
        "bad\rINJECTED_SECRET=leak",
        "bad\0INJECTED_SECRET=leak",
    ],
)
def test_set_secret_rejects_multiline_values_without_partial_write(tmp_path, monkeypatch, capsys, secret_value):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(exist_ok=True)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    env_atlas = get_env_atlas_path()
    original = "OPENAI_API_KEY=old-value\nOTHER=value\n"
    env_atlas.write_text(original, encoding="utf-8")

    with pytest.raises(InvalidSecretValueError, match="single-line"):
        set_secret("OPENAI_API_KEY", secret_value)

    captured = capsys.readouterr()
    assert secret_value not in captured.out
    assert secret_value not in captured.err
    assert env_atlas.read_text(encoding="utf-8") == original
    assert os.environ.get("OPENAI_API_KEY") is None
    config_toml = get_config_toml_path()
    if config_toml.exists():
        assert secret_value not in config_toml.read_text(encoding="utf-8")


def test_cli_config_set_rejects_multiline_secret_without_echo(tmp_path, monkeypatch, capsys):
    from atlas_agent.cli import main

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(exist_ok=True)
    secret_value = "bad\nINJECTED_SECRET=leak"

    code = main(["config", "set", "providers.openai.api_key", secret_value])

    captured = capsys.readouterr()
    assert code == 2
    assert "single-line" in captured.out
    assert secret_value not in captured.out
    assert secret_value not in captured.err
    assert not get_env_atlas_path().exists()
    config_toml = get_config_toml_path()
    if config_toml.exists():
        assert secret_value not in config_toml.read_text(encoding="utf-8")

def test_nested_config_set(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(exist_ok=True)
    set_raw_value("model.model", "gpt-5")
    
    config = get_config()
    assert config.model.model == "gpt-5"
    
    toml_path = get_config_toml_path()
    assert "[model]" in toml_path.read_text()
    assert 'model = "gpt-5"' in toml_path.read_text()

def test_config_compatibility_properties(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(exist_ok=True)
    set_raw_value("broker.provider", "alpaca")
    set_raw_value("broker.enable_live_trading", True)
    
    config = get_config()
    assert config.live_broker == "alpaca"
    assert config.enable_live_trading == True

def test_redaction(tmp_path, monkeypatch):
    from atlas_agent.config import redact_value
    assert redact_value("1234567890") == "1234...7890"
    assert redact_value("short") == "*****"


def test_get_config_invalid_toml_raises_controlled_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(exist_ok=True)
    (tmp_path / ".atlas" / "config.toml").write_text(
        'trading_mode = "paper"\n[model\nprovider = "openai"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid TOML syntax"):
        get_config()


def test_get_config_invalid_schema_raises_controlled_error_without_value(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(exist_ok=True)
    secret_like_value = "sk-secret-should-not-leak"
    (tmp_path / ".atlas" / "config.toml").write_text(
        f'[broker]\nenable_live_trading = "{secret_like_value}"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc:
        get_config()

    message = str(exc.value)
    assert "Invalid Atlas config schema" in message
    assert secret_like_value not in message
