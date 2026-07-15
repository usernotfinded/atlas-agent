# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_paper_portfolio_proposal.py
# PURPOSE: Verifies paper portfolio proposal behavior and regression
#         expectations.
# DEPS:    json, subprocess, pathlib, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

import json
import subprocess
from pathlib import Path
import pytest

from atlas_agent.backtest.portfolio import (
    build_paper_portfolio_proposal,
    write_portfolio_proposal_reports,
)

# --- CONFIGURATION AND CONSTANTS ---

DATA_PATH = Path("data/sample/ohlcv_extended.csv")

# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_paper_portfolio_proposal_schema(tmp_path):
    report = build_paper_portfolio_proposal(
        data_path=DATA_PATH,
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold"],
        max_strategy_weight=0.40,
        min_cash_weight=0.10,
    )
    
    assert report["artifact_type"] == "paper_portfolio_proposal"
    assert report["mode"] == "paper"
    assert report["live_readiness"] is False
    assert report["safety"]["no_live_trading"] is True
    assert report["safety"]["no_broker_calls"] is True
    
    allocations = report["allocations"]
    assert allocations
    weights = sum(a["paper_weight"] for a in allocations)
    assert 0.999 < weights < 1.001
    
    has_cash = any(a["strategy"] == "cash" for a in allocations)
    assert has_cash
    
    for alloc in allocations:
        if alloc["strategy"] != "cash":
            assert alloc["paper_weight"] <= 0.40
        else:
            assert alloc["paper_weight"] >= 0.10
    
    json_path, md_path = write_portfolio_proposal_reports(report, output_dir=tmp_path)
    assert json_path.exists()
    assert md_path.exists()

def test_portfolio_checker():
    result = subprocess.run(
        ["python3.11", "scripts/check_paper_portfolio_proposal.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

def test_portfolio_demo_script():
    demo = Path("scripts/demo_paper_portfolio_proposal.sh")
    assert demo.exists()
    content = demo.read_text()
    assert "--mode live" not in content
    assert "atlas_agent.cli backtest portfolio-proposal" in content
