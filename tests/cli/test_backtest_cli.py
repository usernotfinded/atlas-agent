import subprocess
import json
import pytest
from pathlib import Path

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
