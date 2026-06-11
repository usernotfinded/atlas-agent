import subprocess
import json
import pytest
from pathlib import Path

from atlas_agent.backtest.report_schema import REPORT_SCHEMA_VERSION, validate_backtest_report

def test_cli_backtest_run_json(tmp_path):
    # Create sample data
    data_path = tmp_path / "data.csv"
    data_path.write_text(
        "date,symbol,open,high,low,close,volume\n"
        "2026-01-01,AAPL,100,105,95,101,1000\n"
        "2026-01-02,AAPL,101,106,96,102,1000\n"
    )
    
    cmd = [
        "python3.11", "-m", "atlas_agent.cli", 
        "backtest", "run", 
        "--symbol", "AAPL", 
        "--data", str(data_path), 
        "--json"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0
    
    output = json.loads(result.stdout)
    assert output["status"] == "completed"
    assert output["config"]["symbol"] == "AAPL"
    assert "metrics" in output

def test_cli_backtest_run_text(tmp_path):
    # Create sample data
    data_path = tmp_path / "data.csv"
    data_path.write_text(
        "date,symbol,open,high,low,close,volume\n"
        "2026-01-01,AAPL,100,105,95,101,1000\n"
        "2026-01-02,AAPL,101,106,96,102,1000\n"
    )
    
    cmd = [
        "python3.11", "-m", "atlas_agent.cli", 
        "backtest", "run", 
        "--symbol", "AAPL", 
        "--data", str(data_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0
    assert "Backtest complete: AAPL" in result.stdout
    assert "Total Return:" in result.stdout


def test_cli_backtest_list_strategies_json():
    cmd = [
        "python3.11", "-m", "atlas_agent.cli",
        "backtest", "list-strategies",
        "--json",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    assert result.returncode == 0
    output = json.loads(result.stdout)
    strategy_ids = [item["strategy_id"] for item in output]
    assert "buy_and_hold" in strategy_ids
    assert "moving_average_cross" in strategy_ids
    assert "rsi_mean_reversion" in strategy_ids


def test_cli_backtest_describe_strategy():
    cmd = [
        "python3.11", "-m", "atlas_agent.cli",
        "backtest", "describe", "buy_and_hold",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    assert result.returncode == 0
    assert "Strategy: buy_and_hold" in result.stdout
    assert "Buy and Hold" in result.stdout
    assert "position_pct" in result.stdout


def test_cli_backtest_validate_strategy_json(tmp_path):
    data_path = tmp_path / "data.csv"
    data_path.write_text(
        "date,symbol,open,high,low,close,volume\n"
        "2026-01-01,AAPL,100,105,95,101,1000\n"
    )

    cmd = [
        "python3.11", "-m", "atlas_agent.cli",
        "backtest", "validate", "buy_and_hold",
        "--symbol", "AAPL",
        "--data", str(data_path),
        "--json",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "valid"
    assert output["strategy_id"] == "buy_and_hold"


def test_cli_backtest_run_unknown_strategy_fails_closed(tmp_path):
    data_path = tmp_path / "data.csv"
    data_path.write_text(
        "date,symbol,open,high,low,close,volume\n"
        "2026-01-01,AAPL,100,105,95,101,1000\n"
    )

    cmd = [
        "python3.11", "-m", "atlas_agent.cli",
        "backtest", "run",
        "--strategy", "missing_strategy",
        "--symbol", "AAPL",
        "--data", str(data_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    assert result.returncode == 1
    assert "Unknown backtest strategy" in result.stdout
    assert result.stderr == ""


def test_cli_backtest_run_moving_average_with_parameters_json(tmp_path):
    data_path = tmp_path / "data.csv"
    data_path.write_text(
        "date,symbol,open,high,low,close,volume\n"
        "2026-01-01,AAPL,10,11,9,10,1000\n"
        "2026-01-02,AAPL,10,11,9,10,1000\n"
        "2026-01-03,AAPL,10,11,9,10,1000\n"
        "2026-01-04,AAPL,9,10,8,9,1000\n"
        "2026-01-05,AAPL,12,13,11,12,1000\n",
        encoding="utf-8",
    )

    cmd = [
        "python3.11", "-m", "atlas_agent.cli",
        "backtest", "run",
        "--strategy", "moving_average_cross",
        "--strategy-param", "short_window=2",
        "--strategy-param", "long_window=3",
        "--strategy-param", "position_pct=0.01",
        "--symbol", "AAPL",
        "--data", str(data_path),
        "--json",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["strategy_metadata"]["strategy_id"] == "moving_average_cross"
    assert len(output["fills"]) == 1


def test_cli_backtest_spy_benchmark_requires_local_data(tmp_path):
    data_path = tmp_path / "data.csv"
    data_path.write_text(
        "date,symbol,open,high,low,close,volume\n"
        "2026-01-01,AAPL,100,105,95,101,1000\n",
        encoding="utf-8",
    )

    cmd = [
        "python3.11", "-m", "atlas_agent.cli",
        "backtest", "run",
        "--benchmark", "spy",
        "--symbol", "AAPL",
        "--data", str(data_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    assert result.returncode == 1
    assert "SPY benchmark requires a local benchmark data path" in result.stdout


def test_cli_backtest_spy_benchmark_json(tmp_path):
    data_path = tmp_path / "data.csv"
    data_path.write_text(
        "date,symbol,open,high,low,close,volume\n"
        "2026-01-01,AAPL,100,105,95,101,1000\n",
        encoding="utf-8",
    )
    spy_path = tmp_path / "spy.csv"
    spy_path.write_text(
        "date,symbol,open,high,low,close,volume\n"
        "2026-01-01,SPY,100,101,99,100,1000\n"
        "2026-01-02,SPY,110,111,109,110,1000\n",
        encoding="utf-8",
    )

    cmd = [
        "python3.11", "-m", "atlas_agent.cli",
        "backtest", "run",
        "--benchmark", "spy",
        "--benchmark-data", str(spy_path),
        "--symbol", "AAPL",
        "--data", str(data_path),
        "--json",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["benchmark"]["benchmark_id"] == "spy"
    assert output["benchmark"]["return_pct"] == 10.0


def test_cli_backtest_run_with_date_filtering(tmp_path):
    data_path = tmp_path / "data.csv"
    data_path.write_text(
        "date,symbol,open,high,low,close,volume\n"
        "2026-01-01,AAPL,100,105,95,101,1000\n"
        "2026-01-02,AAPL,101,106,96,102,1000\n"
        "2026-01-03,AAPL,102,107,97,103,1000\n"
        "2026-01-04,AAPL,103,108,98,104,1000\n"
        "2026-01-05,AAPL,104,109,99,105,1000\n",
        encoding="utf-8",
    )

    cmd = [
        "python3.11", "-m", "atlas_agent.cli",
        "backtest", "run",
        "--symbol", "AAPL",
        "--data", str(data_path),
        "--start-date", "2026-01-02",
        "--end-date", "2026-01-04",
        "--json",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "completed"
    assert len(output["equity_curve"]) == 3
    assert output["equity_curve"][0]["timestamp"].startswith("2026-01-02")
    assert output["equity_curve"][-1]["timestamp"].startswith("2026-01-04")


def test_cli_backtest_runs_json():
    cmd = [
        "python3.11", "-m", "atlas_agent.cli",
        "backtest", "runs",
        "--json",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert isinstance(output, list)


def test_cli_backtest_report_json_validates_schema(tmp_path):
    data_path = tmp_path / "data.csv"
    data_path.write_text(
        "date,symbol,open,high,low,close,volume\n"
        "2026-01-01,AAPL,100,105,95,101,1000\n"
        "2026-01-02,AAPL,101,106,96,102,1000\n"
    )

    cmd = [
        "python3.11", "-m", "atlas_agent.cli",
        "backtest", "run",
        "--symbol", "AAPL",
        "--data", str(data_path),
        "--report", "json",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["schema_version"] == REPORT_SCHEMA_VERSION
    assert output["report_type"] == "backtest_research_summary"
    validate_backtest_report(output)
