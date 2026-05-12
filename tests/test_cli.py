from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import atlas_agent
from atlas_agent.cli import main
from atlas_agent.config import get_config


def test_atlas_help_works(capsys) -> None:
    assert main(["--help"]) == 0
    assert "atlas" in capsys.readouterr().out


def test_atlas_package_imports() -> None:
    assert atlas_agent.__name__ == "atlas_agent"


def test_python_module_help_works() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "atlas_agent.cli", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "atlas" in result.stdout


def test_main_branding_no_legacy_reference() -> None:
    readme = open("README.md", encoding="utf-8").read()

    assert "# Atlas Agent" in readme
    assert ("Omni" + "TradeAI") not in readme


def test_atlas_validate_works(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["validate"]) == 0
    assert "Workspace initialized missing" in capsys.readouterr().out


def test_config_edit_uses_argv_for_editor_launch(tmp_path, monkeypatch) -> None:
    from atlas_agent.config.paths import get_config_toml_path

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EDITOR", "code --wait")

    with patch("atlas_agent.cli.subprocess.run") as mock_run:
        assert main(["config", "edit"]) == 0

    args, kwargs = mock_run.call_args
    assert args[0] == ["code", "--wait", str(get_config_toml_path())]
    assert kwargs["check"] is False
    assert "shell" not in kwargs


def test_config_edit_does_not_execute_shell_metacharacters(tmp_path, monkeypatch) -> None:
    from atlas_agent.config.paths import get_config_toml_path

    monkeypatch.chdir(tmp_path)
    hacked_path = tmp_path / "hacked"
    monkeypatch.setenv("EDITOR", "code --wait; touch hacked")

    with patch("atlas_agent.cli.subprocess.run") as mock_run:
        assert main(["config", "edit"]) == 0

    args, kwargs = mock_run.call_args
    assert args[0] == [
        "code",
        "--wait;",
        "touch",
        "hacked",
        str(get_config_toml_path()),
    ]
    assert kwargs["check"] is False
    assert kwargs.get("shell", False) is False
    assert not hacked_path.exists()


def test_atlas_backtest_works(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr() # Clear init output

    assert main(["backtest", "run", "--symbol", "DEMO-SYMBOL", "--data", "data/sample/ohlcv.csv"]) == 0
    assert "backtest result: filled" in capsys.readouterr().out


def test_atlas_run_once_paper_works(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.ai.discipline import write_user_discipline

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr() # Clear init output

    profile = (
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
    write_user_discipline(".", profile)

    assert main(["run-once", "--mode", "paper", "--symbol", "DEMO-SYMBOL"]) == 0
    assert "paper result: filled" in capsys.readouterr().out


def test_atlas_run_once_live_fails_safely_by_default(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    from atlas_agent.ai.discipline import write_user_discipline

    monkeypatch.delenv("ENABLE_LIVE_TRADING", raising=False)
    monkeypatch.delenv("LIVE_BROKER", raising=False)
    monkeypatch.chdir(tmp_path)

    main(["init", "."])

    profile = (
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
    write_user_discipline(".", profile)

    assert main(["run-once", "--mode", "live", "--symbol", "DEMO-SYMBOL"]) == 2
    output = capsys.readouterr().out
    assert "live result: rejected" in output
    assert "ENABLE_LIVE_TRADING must be true" in output


def test_atlas_setup_guided_with_mocked_wizard(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init", ".", "--template", "routine-trader"]) == 0
    capsys.readouterr()

    def _fake_wizard(state):
        state.provider = "openai"
        state.model = "gpt-5.5"
        state.credentials_configured = True
        return True

    with patch("atlas_agent.setup.wizard.is_interactive", return_value=True), patch(
        "atlas_agent.setup.wizard.run_wizard", side_effect=_fake_wizard
    ), patch("builtins.input", side_effect=["1", "AAPL"]):
        code = main(["setup"])

    assert code == 0
    output = capsys.readouterr().out
    assert "Setup readiness summary" in output
    assert "DEMO-SYMBOL" not in output

    config = get_config()
    assert config.model.provider == "openai"
    assert config.model.model == "gpt-5.5"
    assert config.market.symbol == "AAPL"
    assert config.trading_mode == "paper"
    assert config.enable_live_trading is False
    assert (tmp_path / ".atlas" / "discipline.md").exists()
    assert not list((tmp_path / ".atlas" / "backtests").rglob("*.json"))


def test_atlas_setup_secret_hygiene_with_mocked_wizard(tmp_path, monkeypatch, capsys):
    from atlas_agent.config import set_secret

    monkeypatch.chdir(tmp_path)
    assert main(["init", ".", "--template", "routine-trader"]) == 0
    capsys.readouterr()

    def _fake_wizard(state):
        state.provider = "openrouter"
        state.model = "openai/gpt-5.5"
        state.credentials_configured = True
        set_secret("OPENROUTER_API_KEY", "sk-or-setup-test")
        return True

    with patch("atlas_agent.setup.wizard.is_interactive", return_value=True), patch(
        "atlas_agent.setup.wizard.run_wizard", side_effect=_fake_wizard
    ), patch("builtins.input", side_effect=["1", "AAPL"]):
        code = main(["setup"])

    assert code == 0
    output = capsys.readouterr().out
    assert "sk-or-setup-test" not in output

    config_toml = (tmp_path / ".atlas" / "config.toml").read_text(encoding="utf-8")
    assert "sk-or-setup-test" not in config_toml

    env_atlas = (tmp_path / ".env.atlas").read_text(encoding="utf-8")
    assert "OPENROUTER_API_KEY=sk-or-setup-test" in env_atlas


def test_atlas_setup_cancelled_returns_2(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init", ".", "--template", "routine-trader"]) == 0
    capsys.readouterr()

    with patch("atlas_agent.setup.wizard.is_interactive", return_value=True), patch(
        "atlas_agent.setup.wizard.run_wizard", return_value=False
    ):
        code = main(["setup"])

    assert code == 2
    assert "Setup cancelled." in capsys.readouterr().out


def test_atlas_setup_discipline_requires_confirmation(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init", ".", "--template", "routine-trader"]) == 0
    capsys.readouterr()

    def _fake_wizard(state):
        state.provider = "openai"
        state.model = "gpt-5.5"
        state.credentials_configured = True
        return True

    with patch("atlas_agent.setup.wizard.is_interactive", return_value=True), patch(
        "atlas_agent.setup.wizard.run_wizard", side_effect=_fake_wizard
    ), patch("builtins.input", side_effect=["3"]):
        code = main(["setup"])

    assert code == 2
    assert not (tmp_path / ".atlas" / "discipline.md").exists()


def test_atlas_setup_noninteractive_fails_closed(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init", ".", "--template", "routine-trader"]) == 0
    capsys.readouterr()

    with patch("atlas_agent.setup.wizard.is_interactive", return_value=False):
        code = main(["setup"])

    assert code == 2
    assert "requires an interactive terminal" in capsys.readouterr().out.lower()
