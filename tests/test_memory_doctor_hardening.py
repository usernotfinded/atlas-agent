# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_memory_doctor_hardening.py
# PURPOSE: Verifies memory doctor hardening behavior and regression
#         expectations.
# DEPS:    json, os, time, pathlib, unittest, pytest, additional local modules.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.config import AtlasConfig
from atlas_agent.memory_doctor import run_memory_doctor


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _config(tmp_path: Path) -> AtlasConfig:
    return AtlasConfig(
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending_orders",
        reports_dir=tmp_path / "reports",
        events_dir=tmp_path / "events",
        data_path=tmp_path / "data" / "ohlcv.csv",
    )


def test_memory_doctor_detects_missing_files_and_stale_pending(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.ensure_dirs()
    stale = config.pending_orders_dir / "old.json"
    stale.write_text('{"approved": false}', encoding="utf-8")
    old = time.time() - (25 * 3600)
    os.utime(stale, (old, old))

    result = run_memory_doctor(
        memory_dir=config.memory_dir,
        pending_orders_dir=config.pending_orders_dir,
        reports_dir=config.reports_dir,
        skills_dir=config.memory_dir.parent / "skills",
    )

    codes = {item.code for item in result.findings}
    assert "missing_memory_file" in codes
    assert "stale_pending_order" in codes


def test_memory_doctor_detects_secret_in_memory(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.ensure_dirs()
    (config.memory_dir / "trade_journal.md").write_text(
        "ALPACA_API_KEY=should_not_be_here\n",
        encoding="utf-8",
    )

    result = run_memory_doctor(
        memory_dir=config.memory_dir,
        pending_orders_dir=config.pending_orders_dir,
        reports_dir=config.reports_dir,
        skills_dir=config.memory_dir.parent / "skills",
    )
    assert any(item.code == "memory_secret_detected" for item in result.errors)


def test_memory_doctor_json_cli_contract(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = _config(tmp_path)
    config.ensure_dirs()

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["memory", "doctor", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["command"] == "atlas memory doctor"
    assert "errors" in payload["data"]
    assert "warnings" in payload["data"]
