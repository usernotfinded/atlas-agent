# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_credentials.py
# PURPOSE: Verifies credentials behavior and regression expectations.
# DEPS:    os, json, pathlib, unittest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from atlas_agent.setup.state import WizardState
from atlas_agent.setup.wizard_ui import WizardApplication
from atlas_agent.cli import main

# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_credentials_status_affects_completeness():
    state = WizardState(
        provider="anthropic",
        model="claude-opus-4-7",
        messaging="cli",
        workspace_path=".",
        trust_mode="paper",
        broker_mode="paper",
        update_channel="stable",
        credentials_configured=False
    )
    assert not state.is_complete
    
    state.credentials_configured = True
    assert state.is_complete

def test_null_provider_completeness_without_credentials():
    state = WizardState(
        provider="null",
        model="none",
        messaging="cli",
        workspace_path=".",
        trust_mode="paper",
        broker_mode="paper",
        update_channel="stable",
        credentials_configured=False
    )
    assert state.is_complete

@patch("atlas_agent.setup.wizard_ui.Application")
def test_wizard_writes_secrets_to_env_atlas(mock_app_class, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = WizardState(provider="openrouter")
    app = WizardApplication(state)
    
    # Simulate entering an API key
    app.current_step = "api_key_input"
    app.input_value = "sk-or-12345"
    
    # Simulate hitting Enter on api_key_input
    # Logic from kb handler:
    key_name = "OPENROUTER_API_KEY"
    app.temp_secrets[key_name] = app.input_value.strip()
    app.state.credentials_configured = True
    
    # Simulate saving
    app.save_secrets()
    
    env_file = tmp_path / ".env.atlas"
    assert env_file.exists()
    content = env_file.read_text()
    assert "OPENROUTER_API_KEY=sk-or-12345" in content
    
    gitignore = tmp_path / ".gitignore"
    assert gitignore.exists()
    assert ".env.atlas" in gitignore.read_text()

@patch("atlas_agent.setup.wizard_ui.Application")
def test_wizard_detects_existing_env_var(mock_app_class, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "existing-key")
    
    state = WizardState(provider="anthropic")
    app = WizardApplication(state)
    
    # next_step from provider should go to api_key_check if env exists
    app.current_step = "provider"
    app.next_step()
    
    assert app.current_step == "api_key_check"
    assert "ANTHROPIC_API_KEY detected" in app.title

@patch("atlas_agent.setup.wizard.is_interactive")
def test_cli_noninteractive_missing_credentials_exits_2(mock_is_interactive, tmp_path, monkeypatch, capsys):
    mock_is_interactive.return_value = False
    monkeypatch.chdir(tmp_path)
    
    # Config exists but credentials_configured is False
    state = WizardState(
        provider="anthropic",
        model="claude-opus-4-7",
        messaging="cli",
        workspace_path=".",
        trust_mode="paper",
        broker_mode="paper",
        update_channel="stable",
        credentials_configured=False
    )
    state.save(tmp_path / ".atlas/config.json")
    
    code = main([])
    assert code == 2
    captured = capsys.readouterr()
    assert "Atlas provider credentials are missing" in captured.out

def test_secrets_never_in_config_json(tmp_path):
    state = WizardState(
        provider="openrouter",
        credentials_configured=True
    )
    state.save(tmp_path / "config.json")
    
    with open(tmp_path / "config.json") as f:
        data = json.load(f)
    
    # Check that no keys containing "KEY" or "SECRET" or the actual value are in JSON
    for k, v in data.items():
        assert "KEY" not in k.upper()
        assert "SECRET" not in k.upper()
        if isinstance(v, str):
            assert "sk-or" not in v
