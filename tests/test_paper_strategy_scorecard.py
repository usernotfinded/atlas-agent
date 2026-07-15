# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_paper_strategy_scorecard.py
# PURPOSE: Verifies paper strategy scorecard behavior and regression
#         expectations.
# DEPS:    json, subprocess, pathlib, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

import json
import subprocess
from pathlib import Path
import pytest

from atlas_agent.backtest.scorecard import (
    build_paper_strategy_scorecard,
    write_strategy_scorecard_reports,
)

# --- CONFIGURATION AND CONSTANTS ---

FIXTURE_DIR = Path("data/sample/regimes")
DATA_PATH = Path("data/sample/ohlcv_extended.csv")

# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_paper_strategy_scorecard_schema(tmp_path):
    report = build_paper_strategy_scorecard(
        data_path=DATA_PATH,
        symbol="DEMO-SYMBOL",
        fixtures=[
            FIXTURE_DIR / "ohlcv_uptrend.csv",
            FIXTURE_DIR / "ohlcv_downtrend.csv",
        ],
        strategies=["buy_and_hold"],
    )
    
    assert report["artifact_type"] == "paper_strategy_scorecard"
    assert report["mode"] == "paper"
    assert report["live_readiness"] is False
    assert report["safety"]["no_live_trading"] is True
    assert report["safety"]["no_broker_calls"] is True
    
    assert report["evidence_streams"]["evaluation"] is True
    assert report["evidence_streams"]["sensitivity"] is True
    assert report["evidence_streams"]["robustness"] is True
    assert report["evidence_streams"]["walk_forward"] is True
    
    assert len(report["strategies"]) == 1
    strategy = report["strategies"][0]
    assert strategy["name"] == "buy_and_hold"
    
    assert strategy["evidence"]["evaluation"]["status"] == "present"
    assert strategy["scorecard"]["live_ready"] is False
    assert strategy["scorecard"]["decision"] in {
        "paper_follow_up_candidate",
        "paper_watchlist",
        "needs_more_testing",
        "rejected",
    }
    
    json_path, md_path = write_strategy_scorecard_reports(report, output_dir=tmp_path)
    assert json_path.exists()
    assert md_path.exists()

def test_scorecard_checker():
    result = subprocess.run(
        ["python3.11", "scripts/check_paper_strategy_scorecard.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

def test_scorecard_demo_script():
    demo = Path("scripts/demo_paper_strategy_scorecard.sh")
    assert demo.exists()
    content = demo.read_text()
    assert "--mode live" not in content
    assert "atlas_agent.cli backtest scorecard" in content
