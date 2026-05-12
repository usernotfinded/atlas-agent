import json
from pathlib import Path
from unittest.mock import patch

from atlas_agent.cli import main
from atlas_agent.setup.state import WizardState

@patch("atlas_agent.setup.wizard.is_interactive")
@patch("atlas_agent.setup.wizard.run_wizard")
def test_bare_atlas_first_run_launches_wizard(mock_run_wizard, mock_is_interactive, tmp_path, monkeypatch, capsys):
    mock_is_interactive.return_value = True
    mock_run_wizard.return_value = True
    monkeypatch.chdir(tmp_path)
    
    code = main([])
    assert code == 0
    assert mock_run_wizard.called
    assert (tmp_path / ".atlas/config.json").exists()
    
    captured = capsys.readouterr()
    assert "First-time setup required." in captured.out

@patch("atlas_agent.setup.wizard.is_interactive")
@patch("atlas_agent.setup.wizard.run_wizard")
def test_bare_atlas_configured_does_not_launch_wizard(mock_run_wizard, mock_is_interactive, tmp_path, monkeypatch, capsys):
    mock_is_interactive.return_value = True
    monkeypatch.chdir(tmp_path)
    
    state = WizardState(
        provider="anthropic",
        model="claude-opus-4-7",
        messaging="cli",
        workspace_path=".",
        trust_mode="paper",
        broker_mode="paper",
        update_channel="stable",
        credentials_configured=True
    )
    state.save(tmp_path / ".atlas/config.json")
    
    code = main([])
    assert code == 0
    assert not mock_run_wizard.called
    
    captured = capsys.readouterr()
    assert "Current setup status:" in captured.out

@patch("atlas_agent.setup.wizard.is_interactive")
@patch("atlas_agent.setup.wizard.run_wizard")
def test_bare_atlas_incomplete_config_launches_wizard(mock_run_wizard, mock_is_interactive, tmp_path, monkeypatch, capsys):
    mock_is_interactive.return_value = True
    mock_run_wizard.return_value = True
    monkeypatch.chdir(tmp_path)
    
    # Missing messaging, broker_mode, etc.
    state = WizardState(
        provider="anthropic",
        model="claude-opus-4-7",
        messaging=""
    )
    state.save(tmp_path / ".atlas/config.json")
    
    code = main([])
    assert code == 0
    assert mock_run_wizard.called
    
    captured = capsys.readouterr()
    assert "First-time setup required." in captured.out

@patch("atlas_agent.setup.wizard.is_interactive")
@patch("atlas_agent.setup.wizard.run_wizard")
def test_bare_atlas_noninteractive_no_config_exits_2(mock_run_wizard, mock_is_interactive, tmp_path, monkeypatch, capsys):
    mock_is_interactive.return_value = False
    monkeypatch.chdir(tmp_path)
    
    code = main([])
    assert code == 2
    assert not mock_run_wizard.called
    
    captured = capsys.readouterr()
    assert "Atlas provider credentials are missing. Run `atlas configure` in an interactive terminal or set the required environment variable." in captured.out

@patch("atlas_agent.setup.wizard.is_interactive")
@patch("atlas_agent.setup.wizard.run_wizard")
def test_configure_always_launches_wizard_even_if_configured(mock_run_wizard, mock_is_interactive, tmp_path, monkeypatch, capsys):
    mock_is_interactive.return_value = True
    mock_run_wizard.return_value = True
    monkeypatch.chdir(tmp_path)
    
    state = WizardState(
        provider="anthropic",
        model="claude-opus-4-7",
        messaging="cli",
        workspace_path=".",
        trust_mode="paper",
        broker_mode="paper",
        update_channel="stable"
    )
    state.save(tmp_path / ".atlas/config.json")
    
    code = main(["configure"])
    assert code == 0
    assert mock_run_wizard.called

@patch("atlas_agent.setup.wizard.is_interactive")
@patch("atlas_agent.setup.wizard.run_wizard")
def test_cancel_first_run_does_not_write_partial_config(mock_run_wizard, mock_is_interactive, tmp_path, monkeypatch, capsys):
    mock_is_interactive.return_value = True
    mock_run_wizard.return_value = False
    monkeypatch.chdir(tmp_path)
    
    code = main([])
    assert code == 130
    assert not (tmp_path / ".atlas/config.json").exists()
    
    captured = capsys.readouterr()
    assert "Setup cancelled. Atlas is not configured yet." in captured.out
