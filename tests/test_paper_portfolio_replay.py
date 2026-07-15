# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_paper_portfolio_replay.py
# PURPOSE: Verifies paper portfolio replay behavior and regression expectations.
# DEPS:    pytest, os, json, tempfile, pathlib, unittest, additional local
#         modules.
# ==============================================================================

# --- IMPORTS ---

import pytest
import os
import json
import tempfile
from pathlib import Path
from unittest import mock

from atlas_agent.backtest.portfolio import (
    build_paper_portfolio_replay,
    write_portfolio_replay_reports
)

# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_build_paper_portfolio_replay_deterministic():
    data_path = "data/sample/ohlcv_extended.csv"
    if not os.path.exists(data_path):
        pytest.skip("No sample data")
        
    report = build_paper_portfolio_replay(
        data_path=data_path,
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold"],
        repeat=2
    )
    
    assert report["artifact_type"] == "paper_portfolio_replay"
    assert report["schema_version"] == 1
    assert report["mode"] == "paper"
    assert report["provider_required"] is False
    assert report["broker_required"] is False
    assert report["network_required"] is False
    assert report["live_readiness"] is False
    assert report["not_financial_advice"] is True
    assert report["overall_replay_status"] in ["paper_replay_pass", "needs_recheck"]
    assert report["repeat"] == 2
    assert len(report["runs"]) == 2
    assert len(report["comparisons"]) > 0
    assert all(c["status"] == "match" for c in report["comparisons"])

def test_write_portfolio_replay_reports():
    data_path = "data/sample/ohlcv_extended.csv"
    if not os.path.exists(data_path):
        pytest.skip("No sample data")
        
    report = build_paper_portfolio_replay(
        data_path=data_path,
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold"],
        repeat=1
    )
    
    with tempfile.TemporaryDirectory() as temp_dir:
        json_path, md_path, manifest_path = write_portfolio_replay_reports(report, temp_dir)
        
        assert os.path.exists(json_path)
        assert os.path.exists(md_path)
        assert os.path.exists(manifest_path)
        
        with open(json_path, "r") as f:
            data = json.load(f)
        assert data["artifact_type"] == "paper_portfolio_replay"
        
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
        assert manifest["manifest_type"] == "paper_portfolio_regression_manifest"

def test_paper_portfolio_replay_drift_detected():
    # Simulate a drift by mocking build_paper_portfolio_dossier
    with mock.patch("atlas_agent.backtest.portfolio.build_paper_portfolio_dossier") as mock_dossier:
        # First call returns normal dossier, second call returns slightly different dossier
        mock_dossier.side_effect = [
            {
                "schema_version": 1,
                "overall_dossier_status": "paper_dossier_complete",
                "artifacts": [
                    {"name": "test.json", "artifact_type": "test", "digest": "aaa"}
                ]
            },
            {
                "schema_version": 1,
                "overall_dossier_status": "paper_dossier_complete",
                "artifacts": [
                    {"name": "test.json", "artifact_type": "test", "digest": "bbb"}
                ]
            }
        ]
        
        report = build_paper_portfolio_replay(
            data_path="test",
            symbol="TEST",
            strategies=[],
            repeat=2
        )
        
        assert report["overall_replay_status"] == "paper_replay_drift_detected"
        
        mismatches = [c for c in report["comparisons"] if c["status"] == "mismatch"]
        assert len(mismatches) > 0

def test_paper_portfolio_replay_schema_mismatch():
    with mock.patch("atlas_agent.backtest.portfolio.build_paper_portfolio_dossier") as mock_dossier:
        mock_dossier.return_value = {
            "schema_version": 999,  # Bad schema
            "overall_dossier_status": "paper_dossier_complete",
            "artifacts": []
        }
        
        report = build_paper_portfolio_replay(
            data_path="test",
            symbol="TEST",
            strategies=[],
            repeat=1
        )
        
        assert report["overall_replay_status"] == "paper_replay_schema_mismatch"
