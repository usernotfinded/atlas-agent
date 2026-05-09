import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from atlas_agent.cli import main, YELLOW, RESET
from atlas_agent.setup.state import WizardState
from atlas_agent.update.manager import SafeUpdateManager, UpdateApplyReport

def test_wizard_banner_persistence(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    # Mock TTY and Wizard success
    with patch("atlas_agent.setup.wizard.is_interactive", return_value=True), \
         patch("atlas_agent.setup.wizard.WizardApplication.run", return_value=True), \
         patch("atlas_agent.cli._check_for_updates", return_value=None):
        
        # Setup incomplete config
        config_path = tmp_path / ".atlas/config.json"
        state = WizardState(provider="") # Incomplete
        state.save(config_path)
        
        code = main([])
        assert code == 0
        
        captured = capsys.readouterr()
        # Banner should be printed at least once (before wizard) 
        # and then again after wizard completion in the status report.
        assert "___ _____ _      _   ___" in captured.out
        assert "Setup completed successfully." in captured.out
        assert "Current setup status:" in captured.out

def test_yellow_update_command(tmp_path, monkeypatch, capsys, write_complete_setup_config):
    monkeypatch.chdir(tmp_path)
    # Mock update available
    with patch("atlas_agent.cli._check_for_updates", return_value="0.3.0"):
        # We need a complete config to trigger onboarding print from bare atlas
        write_complete_setup_config(tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        
        main([])
        captured = capsys.readouterr()
        
        expected_cmd = f"{YELLOW}atlas update{RESET}"
        assert expected_cmd in captured.out
        assert "Run: " + expected_cmd in captured.out

def test_updater_secret_preservation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    
    # Mock config and manager
    config = MagicMock()
    manager = SafeUpdateManager(config=config, workspace_root=tmp_path)
    
    # Simulate git repo
    with patch.object(SafeUpdateManager, "_is_git_repo", return_value=True), \
         patch.object(SafeUpdateManager, "_get_git_sensitive_changes", return_value=[".env.atlas"]):
        
        report = manager.apply()
        assert not report.applied
        assert "update would overwrite sensitive file: .env.atlas" in report.blockers
        assert "Preserved local secrets file: .env.atlas" in report.warnings
        assert "Skipped sensitive file during update due to local protection." in report.warnings

def test_updater_is_sensitive_logic(tmp_path):
    manager = SafeUpdateManager(config=MagicMock(), workspace_root=tmp_path)
    
    assert manager._is_sensitive(tmp_path / ".env")
    assert manager._is_sensitive(tmp_path / ".env.atlas")
    assert manager._is_sensitive(tmp_path / ".env.local")
    assert manager._is_sensitive(tmp_path / ".env.prod")
    assert manager._is_sensitive(tmp_path / ".atlas/config.json")
    
    assert not manager._is_sensitive(tmp_path / "README.md")
    assert not manager._is_sensitive(tmp_path / "src/main.py")

def test_next_commands_contains_yellow_update(tmp_path, monkeypatch, capsys):
    # This specifically checks _print_first_run_onboarding
    from atlas_agent.cli import _print_first_run_onboarding, WorkspaceResolution
    
    # Case 1: Workspace not configured
    _print_first_run_onboarding(
        config=None,
        config_error=None,
        resolution=WorkspaceResolution(path=None, source="cwd")
    )
    
    captured = capsys.readouterr()
    expected_cmd = f"{YELLOW}atlas update{RESET}"
    assert expected_cmd in captured.out
    assert "atlas init <workspace>" in captured.out

    # Case 2: Workspace configured
    _print_first_run_onboarding(
        config=None,
        config_error=None,
        resolution=WorkspaceResolution(path=tmp_path, source="cwd")
    )
    captured = capsys.readouterr()
    assert expected_cmd in captured.out
    assert "atlas init <workspace>" not in captured.out
    assert "Optional:" in captured.out
    assert "atlas configure" in captured.out
