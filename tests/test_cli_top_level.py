from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
import json
from unittest.mock import ANY, patch

import pytest

from atlas_agent.cli import main
from atlas_agent.ai.discipline import write_user_discipline

GOOD_PROFILE = (
    "# Profile\n\n"
    "## Decision temperament\n\nCautious.\n\n"
    "## Reasoning style\n\nStep-by-step.\n\n"
    "## Communication style\n\nConcise.\n\n"
    "## Risk posture\n\nConservative.\n\n"
    "## Uncertainty handling\n\nExplicit.\n\n"
    "## No-trade bias\n\nDefault to hold.\n\n"
    "## Forbidden overrides\n\n"
    "User discipline cannot override Atlas risk gates, approval queues, kill switch, "
    "audit logging, broker sync checks, reference price requirements, or live-trading safeguards.\n"
)

@pytest.fixture
def workspace():
    temp_dir = tempfile.mkdtemp()
    original_cwd = os.getcwd()
    os.chdir(temp_dir)
    try:
        main(["init", "."])
        write_user_discipline(".", GOOD_PROFILE)
        main(["config", "set", "market.symbol", "TEST-SYMBOL"])
        yield Path(temp_dir)
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(temp_dir)


@pytest.fixture
def non_workspace():
    temp_dir = tempfile.mkdtemp()
    original_cwd = os.getcwd()
    os.chdir(temp_dir)
    try:
        yield Path(temp_dir)
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(temp_dir)


def test_help_no_agent_start(non_workspace, capsys):
    code = main(["--help"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Atlas Agent is a broker-neutral supervised trading workspace" in captured.out
    assert "Starting autonomous cycle..." not in captured.out


def test_bare_atlas_does_not_start_cycle(workspace, capsys, monkeypatch, write_complete_setup_config):
    write_complete_setup_config(workspace)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    code = main([])
    assert code == 0
    output = capsys.readouterr().out
    assert "Starting autonomous cycle..." not in output
    assert "Bare `atlas` no longer starts autonomous execution." in output


def test_bare_atlas_prints_onboarding(workspace, capsys, monkeypatch, write_complete_setup_config):
    write_complete_setup_config(workspace)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    code = main([])
    assert code == 0
    output = capsys.readouterr().out
    assert "Current setup status:" in output
    assert "- workspace configured: yes" in output
    assert "- broker mode: paper" in output
    assert "- live broker credentials: not configured" in output
    assert "Next commands:" in output
    assert "atlas init <workspace>" not in output # Should be hidden when workspace is configured
    assert "atlas validate" in output
    assert "atlas run --mode paper" in output
    assert "Optional:" in output
    assert "atlas configure" in output


def test_bare_atlas_does_not_call_runner(workspace, capsys, monkeypatch, write_complete_setup_config):
    write_complete_setup_config(workspace)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch("atlas_agent.agent.runner.run_agent") as mock_run:
        code = main([])
        assert code == 0
        mock_run.assert_not_called()
    _ = capsys.readouterr()


def test_onboarding_binance_credentials_use_canonical_secret_env(workspace, capsys, monkeypatch, write_complete_setup_config):
    write_complete_setup_config(workspace)
    assert main(["config", "set", "broker.provider", "binance"]) == 0
    monkeypatch.setenv("BINANCE_API_KEY", "demo-binance-key")
    monkeypatch.setenv("BINANCE_API_SECRET", "demo-binance-secret")
    monkeypatch.delenv("BINANCE_SECRET_KEY", raising=False)

    code = main([])
    assert code == 0
    output = capsys.readouterr().out
    assert "- live broker credentials: configured" in output
    assert "demo-binance-key" not in output
    assert "demo-binance-secret" not in output


def test_onboarding_binance_legacy_secret_alias_is_compatibility_only(
    workspace,
    capsys,
    monkeypatch,
    write_complete_setup_config,
):
    write_complete_setup_config(workspace)
    assert main(["config", "set", "broker.provider", "binance"]) == 0
    monkeypatch.setenv("BINANCE_API_KEY", "demo-binance-key")
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    monkeypatch.setenv("BINANCE_SECRET_KEY", "legacy-binance-secret")

    code = main([])
    assert code == 0
    output = capsys.readouterr().out
    assert "- live broker credentials: configured" in output
    assert "legacy-binance-secret" not in output


def test_bare_atlas_outside_workspace(non_workspace, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(non_workspace))
    # Incomplete setup (no config at all) -> exit 2 in non-interactive
    code = main([])
    assert code == 2
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Atlas provider credentials are missing" in combined


def test_run_requires_workspace(non_workspace, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(non_workspace))
    code = main(["run"])
    assert code == 2
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "No Atlas workspace configured. Run `atlas init <name>` first." in output


def test_run_with_missing_workspace_exits_2(non_workspace, capsys):
    code = main(["--workspace", str(non_workspace / "missing-workspace"), "run"])
    assert code == 2
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "No Atlas workspace configured. Run `atlas init <name>` first." in output


def test_configure_noninteractive_exits_2(non_workspace, capsys):
    code = main(["configure"])
    assert code == 2
    output = capsys.readouterr().out
    assert "Non-interactive mode detected. Cannot run UI wizard." in output



def test_status_alias(workspace):
    with patch("atlas_agent.agent.status.get_agent_status") as mock_status:
        mock_status.return_value = "Mock Status"
        code = main(["status"])
        assert code == 0
        mock_status.assert_called_once()


def test_plan_alias(workspace):
    with patch("atlas_agent.agent.planner.get_agent_plan") as mock_plan:
        mock_plan.return_value = "Mock Plan"
        code = main(["plan"])
        assert code == 0
        mock_plan.assert_called_once()


def test_run_alias(workspace):
    with patch("atlas_agent.agent.runner.run_agent") as mock_run:
        from atlas_agent.routines.routine_result import RoutineResult

        mock_run.return_value = RoutineResult(
            name="pre_market",
            mode="paper",
            status="complete",
            report_path=Path("reports/daily/test.md"),
            memory_files_updated=(),
        )
        code = main(["run"])
        assert code == 0
        mock_run.assert_called_with(
            mode="auto",
            config=ANY,
            continuous=False,
            interval=60,
            max_cycles=None,
            symbol=ANY,
        )


def test_run_continuous_alias(workspace):
    with patch("atlas_agent.agent.runner.run_agent") as mock_run:
        from atlas_agent.routines.routine_result import RoutineResult

        mock_run.return_value = RoutineResult(
            name="pre_market",
            mode="paper",
            status="complete",
            report_path=Path("reports/daily/test.md"),
            memory_files_updated=(),
        )
        code = main(["run", "--continuous"])
        assert code == 0
        mock_run.assert_called_with(
            mode="auto",
            config=ANY,
            continuous=True,
            interval=60,
            max_cycles=None,
            symbol=ANY,
        )


def test_run_dry_run_alias(workspace):
    with patch("atlas_agent.agent.planner.get_agent_plan") as mock_plan:
        mock_plan.return_value = "Mock Plan"
        code = main(["run", "--dry-run"])
        assert code == 0
        mock_plan.assert_called_once()


def test_run_dry_run_invalid_toml_returns_controlled_config_error(workspace, capsys):
    config_toml = workspace / ".atlas" / "config.toml"
    config_toml.write_text(
        'trading_mode = "paper"\n[model\nprovider = "openai"\n',
        encoding="utf-8",
    )

    with patch("atlas_agent.agent.planner.get_agent_plan") as mock_plan:
        code = main(["run", "--dry-run"])

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert code == 1
    assert "Configuration error:" in combined
    assert "Invalid TOML syntax" in combined
    mock_plan.assert_not_called()


def test_run_dry_run_invalid_schema_does_not_fallback_to_defaults(workspace, capsys):
    secret_like_value = "sk-secret-runtime-should-not-leak"
    config_toml = workspace / ".atlas" / "config.toml"
    config_toml.write_text(
        f'[broker]\nenable_live_trading = "{secret_like_value}"\n',
        encoding="utf-8",
    )

    with patch("atlas_agent.agent.planner.get_agent_plan") as mock_plan:
        code = main(["run", "--dry-run"])

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert code == 1
    assert "Configuration error:" in combined
    assert "Invalid Atlas config schema" in combined
    assert secret_like_value not in combined
    assert "gpt-4o" not in combined
    mock_plan.assert_not_called()


def test_model_current_invalid_schema_returns_controlled_error(workspace, capsys):
    secret_like_value = "sk-secret-model-should-not-leak"
    config_toml = workspace / ".atlas" / "config.toml"
    config_toml.write_text(
        f'[broker]\nenable_live_trading = "{secret_like_value}"\n',
        encoding="utf-8",
    )

    code = main(["model", "current"])
    captured = capsys.readouterr()
    combined = captured.out + captured.err

    assert code == 1
    assert "Configuration error:" in combined
    assert "Invalid Atlas config schema" in combined
    assert secret_like_value not in combined
    assert "provider: " not in combined


def test_existing_agent_commands_still_work(workspace):
    with patch("atlas_agent.agent.runner.run_agent") as mock_run:
        from atlas_agent.routines.routine_result import RoutineResult

        mock_run.return_value = RoutineResult(
            name="pre_market",
            mode="paper",
            status="complete",
            report_path=Path("reports/daily/test.md"),
            memory_files_updated=(),
        )
        code = main(["agent", "run", "--once"])
        assert code == 0
        mock_run.assert_called()
