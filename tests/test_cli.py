from __future__ import annotations

import subprocess
import sys

import atlas_agent
from atlas_agent.cli import main


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
    assert "Configuration valid" in capsys.readouterr().out


def test_atlas_backtest_works(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["backtest", "--strategy", "moving_average", "--symbol", "BTC-USD"]) == 0
    assert "Backtest complete" in capsys.readouterr().out


def test_atlas_run_once_paper_works(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["run-once", "--mode", "paper"]) == 0
    assert "paper result: filled" in capsys.readouterr().out


def test_atlas_run_once_live_fails_safely_by_default(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["run-once", "--mode", "live"]) == 2
    output = capsys.readouterr().out
    assert "live result: rejected" in output
    assert "ENABLE_LIVE_TRADING must be true" in output
