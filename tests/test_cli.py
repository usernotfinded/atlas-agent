from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

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
    main(["init", "."])
    capsys.readouterr() # Clear init output

    assert main(["backtest"]) == 0
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

    assert main(["run-once", "--mode", "paper"]) == 0
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

    assert main(["run-once", "--mode", "live"]) == 2
    output = capsys.readouterr().out
    assert "live result: rejected" in output
    assert "ENABLE_LIVE_TRADING must be true" in output
