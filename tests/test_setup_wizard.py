import json
import sys
from pathlib import Path
from unittest.mock import patch

from atlas_agent.setup.wizard_ui import WizardApplication
from atlas_agent.setup.renderer import render_wizard_screen
from atlas_agent.setup.state import WizardState

def test_wizard_hides_local_command_and_null():
    state = WizardState()
    state.setup_mode = "full"
    app = WizardApplication(state)
    app.current_step = "provider"
    app.update_step_data()
    choice_ids = [c[0] for c in app.choices]
    assert "local_command" not in choice_ids
    assert "null" not in choice_ids
    assert "lmstudio" in choice_ids
    assert "openai-compatible" in choice_ids

def test_wizard_api_key_input_is_visible():
    state = WizardState()
    lines = render_wizard_screen(
        state=state,
        current_step="api_key_input",
        choices=[],
        current_index=0,
        input_value="my-secret-key",
        title="Enter Key",
        is_password=False
    )
    text = "".join(line[1] for line in lines)
    assert "my-secret-key" in text
    assert "******" not in text

def test_wizard_summary_redacts_api_key():
    state = WizardState()
    state.credentials_configured = True
    lines = render_wizard_screen(
        state=state,
        current_step="model",
        choices=[],
        current_index=0,
        input_value="",
        title="Select Model",
        is_password=False
    )
    text = "".join(line[1] for line in lines)
    assert "API Key: configured" in text
    assert "my-secret-key" not in text
from atlas_agent.setup.wizard import is_interactive
from atlas_agent.cli import main

def test_wizard_state_default():
    state = WizardState()
    assert state.setup_mode == "quick"
    assert state.messaging == "cli"

def test_wizard_state_serialization(tmp_path):
    config_file = tmp_path / "config.json"
    state = WizardState(
        setup_mode="full",
        provider="anthropic",
        model="claude-3-5-sonnet",
        messaging="telegram",
        workspace_path="/tmp/workspace",
        trust_mode="live",
        broker_mode="alpaca",
        update_channel="beta"
    )
    state.save(config_file)
    
    assert config_file.exists()
    
    loaded = WizardState.load(config_file)
    assert loaded.setup_mode == "full"
    assert loaded.provider == "anthropic"
    assert loaded.model == "claude-3-5-sonnet"
    assert loaded.messaging == "telegram"
    assert loaded.workspace_path == "/tmp/workspace"
    assert loaded.trust_mode == "live"
    assert loaded.broker_mode == "alpaca"
    assert loaded.update_channel == "beta"

def test_wizard_state_load_nonexistent(tmp_path):
    missing_file = tmp_path / "missing.json"
    state = WizardState.load(missing_file)
    assert state.setup_mode == "quick"

def test_wizard_state_load_invalid(tmp_path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("invalid json")
    state = WizardState.load(bad_file)
    assert state.setup_mode == "quick"

@patch("atlas_agent.setup.wizard.is_interactive")
def test_cli_configure_non_interactive(mock_is_interactive, capsys):
    mock_is_interactive.return_value = False
    
    code = main(["configure"])
    assert code == 2
    
    captured = capsys.readouterr()
    assert "Non-interactive mode detected" in captured.out
    
@patch("atlas_agent.setup.wizard.is_interactive")
@patch("atlas_agent.setup.wizard.run_wizard")
def test_cli_configure_success(mock_run_wizard, mock_is_interactive, tmp_path, monkeypatch):
    mock_is_interactive.return_value = True
    mock_run_wizard.return_value = True
    
    monkeypatch.chdir(tmp_path)
    
    code = main(["configure"])
    assert code == 0
    assert (tmp_path / ".atlas/config.json").exists()
    
@patch("atlas_agent.setup.wizard.is_interactive")
@patch("atlas_agent.setup.wizard.run_wizard")
def test_cli_configure_cancel(mock_run_wizard, mock_is_interactive, tmp_path, monkeypatch, capsys):
    mock_is_interactive.return_value = True
    mock_run_wizard.return_value = False
    
    monkeypatch.chdir(tmp_path)
    
    code = main(["configure"])
    assert code == 130
    
    captured = capsys.readouterr()
    assert "Setup cancelled." in captured.out
