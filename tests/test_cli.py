from __future__ import annotations

import json
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
    main(["init", "."])
    capsys.readouterr() # Clear init output

    # Create tiny CSV fixture
    csv_path = tmp_path / "test_ohlcv.csv"
    csv_path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2024-01-01,100,105,99,104,1000\n"
        "2024-01-02,104,110,103,108,1200\n"
        "2024-01-03,108,112,107,111,1300\n"
    )

    exit_code = main([
        "backtest", 
        "run", 
        "--strategy", "buy_and_hold", 
        "--symbol", "BTC-USD",
        "--data", str(csv_path)
    ])
    
    out, err = capsys.readouterr()
    assert exit_code == 0
    assert "Backtest complete: BTC-USD" in out
    assert "Report saved to:" in out
    # Safety checks
    assert "live trading" not in out.lower()
    assert "broker execution" not in out.lower()
    
    # Verify result.json exists
    backtest_dirs = list((tmp_path / ".atlas" / "backtests").iterdir())
    assert len(backtest_dirs) > 0
    result_json = backtest_dirs[0] / "result.json"
    assert result_json.exists()


def test_atlas_backtest_json_works(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr() # Clear init output

    csv_path = tmp_path / "test_ohlcv.csv"
    csv_path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2024-01-01,100,105,99,104,1000\n"
        "2024-01-02,104,110,103,108,1200\n"
    )

    exit_code = main([
        "backtest", 
        "run", 
        "--symbol", "BTC-USD",
        "--data", str(csv_path),
        "--json"
    ])
    
    out, err = capsys.readouterr()
    assert exit_code == 0
    
    result = json.loads(out)
    assert "run_id" in result
    assert result["status"] == "completed"
    assert result["config"]["symbol"] == "BTC-USD"
    assert "metrics" in result
    assert "final_equity" in result["metrics"]


def test_atlas_run_once_paper_works(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    main(["init", "."])

    assert main(["run-once", "--mode", "paper"]) == 0
    assert "paper result: filled" in capsys.readouterr().out


def test_atlas_run_once_live_fails_safely_by_default(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    main(["init", "."])

    assert main(["run-once", "--mode", "live"]) == 2
    output = capsys.readouterr().out
    assert "live result: rejected" in output
    assert "ENABLE_LIVE_TRADING must be true" in output
