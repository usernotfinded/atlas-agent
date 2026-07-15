# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_first_run.py
# PURPOSE: Verifies first run behavior and regression expectations.
# DEPS:    json, collections, pathlib, unittest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

import json
from collections import namedtuple
from pathlib import Path
from unittest.mock import patch

from atlas_agent.cli import main
from atlas_agent.setup.state import WizardState

# --- CONFIGURATION AND CONSTANTS ---

_FakeLiveStatus = namedtuple("_FakeLiveStatus", ["credentials_configured", "can_submit", "message"])


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

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


def _write_complete_state(config_json: Path, *, broker_mode: str = "paper", trust_mode: str = "paper") -> None:
    """Write a WizardState-compatible config.json that state.is_complete sees as done."""
    config_json.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "setup_mode": "quick",
        "provider": "null",
        "model": "null",
        "google_api_mode": "native",
        "google_auth_method": "api_key",
        "custom_endpoint": None,
        "research_provider": "skip",
        "messaging": "cli",
        "workspace_path": ".",
        "trust_mode": trust_mode,
        "broker_mode": broker_mode,
        "update_channel": "stable",
        "credentials_configured": False,
    }
    config_json.write_text(json.dumps(state), encoding="utf-8")


@patch("atlas_agent.cli._display_live_status")
@patch("atlas_agent.setup.wizard.is_interactive")
@patch("atlas_agent.setup.wizard.run_wizard")
def test_bare_atlas_no_workspace_never_shows_live_trading_enabled(
    mock_run_wizard, mock_is_interactive, mock_display, tmp_path, monkeypatch, capsys
):
    """FINDING-01 regression: bare atlas must not claim live trading is enabled."""
    mock_is_interactive.return_value = False
    mock_display.return_value = _FakeLiveStatus(False, False, "missing for test")
    monkeypatch.chdir(tmp_path)

    _write_complete_state(tmp_path / ".atlas" / "config.json")

    code = main([])
    assert code == 0
    captured = capsys.readouterr()

    assert "live trading enabled:" not in captured.out.lower()
    assert "effective mode: paper (no workspace)" in captured.out
    assert "live submit possible: no" in captured.out


@patch("atlas_agent.cli._display_live_status")
@patch("atlas_agent.setup.wizard.is_interactive")
@patch("atlas_agent.setup.wizard.run_wizard")
def test_bare_atlas_paper_workspace_shows_paper_mode(
    mock_run_wizard, mock_is_interactive, mock_display, tmp_path, monkeypatch, capsys
):
    """FINDING-01 regression: a paper workspace must report paper / no live submit."""
    mock_is_interactive.return_value = False
    mock_display.return_value = _FakeLiveStatus(False, False, "missing for test")
    monkeypatch.chdir(tmp_path)

    (tmp_path / "memory").mkdir()
    _write_complete_state(tmp_path / ".atlas" / "config.json", broker_mode="paper")

    code = main([])
    assert code == 0
    captured = capsys.readouterr()

    assert "live trading enabled:" not in captured.out.lower()
    assert "effective mode: paper" in captured.out
    assert "live submit possible: no" in captured.out


@patch("atlas_agent.cli._display_live_status")
@patch("atlas_agent.setup.wizard.is_interactive")
@patch("atlas_agent.setup.wizard.run_wizard")
def test_bare_atlas_live_flag_without_submit_never_shows_live_trading_enabled(
    mock_run_wizard, mock_is_interactive, mock_display, tmp_path, monkeypatch, capsys
):
    """FINDING-01 regression: enable_live_trading=true but submit impossible must not say live trading enabled."""
    mock_is_interactive.return_value = False
    mock_display.return_value = _FakeLiveStatus(
        credentials_configured=False,
        can_submit=False,
        message="test-missing-condition",
    )
    monkeypatch.chdir(tmp_path)

    (tmp_path / "memory").mkdir()
    _write_complete_state(tmp_path / ".atlas" / "config.json", broker_mode="alpaca")

    # Override the saved broker config to enable live trading while leaving submit disabled.
    config_toml = tmp_path / ".atlas" / "config.toml"
    config_toml.write_text(
        '[broker]\nprovider = "alpaca"\nenable_live_trading = true\n',
        encoding="utf-8",
    )

    code = main([])
    assert code == 0
    captured = capsys.readouterr()

    assert "live trading enabled:" not in captured.out.lower()
    assert "live trading config flag: set" in captured.out
    assert "live submit possible: no (missing:" in captured.out
