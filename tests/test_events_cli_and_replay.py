# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_events_cli_and_replay.py
# PURPOSE: Verifies events cli and replay behavior and regression expectations.
# DEPS:    json, pathlib, unittest, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.config import AtlasConfig
from atlas_agent.events import EventLogger


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


def _seed_run(logger: EventLogger, run_id: str = "run-1") -> None:
    common = {"run_id": run_id, "command": "atlas agent run", "mode": "paper"}
    logger.write("agent_started", payload={"source": "test"}, **common)
    logger.write("market_state_detected", payload={"state": "closed"}, **common)
    logger.write("memory_loaded", payload={"files": ["trade_journal.md"]}, **common)
    logger.write("decision_proposed", payload={"action": "hold"}, **common)
    logger.write("risk_approved", payload={"order_id": "n/a"}, **common)
    logger.write("agent_completed", payload={"status": "complete"}, **common)


def test_events_list_tail_and_doctor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = _config(tmp_path)
    config.ensure_dirs()
    logger = EventLogger(config.events_dir)
    _seed_run(logger)

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["events", "list"]) == 0
        out_list = capsys.readouterr().out
        assert "agent_started" in out_list

        assert main(["events", "tail", "--limit", "2"]) == 0
        out_tail = capsys.readouterr().out
        assert "agent_completed" in out_tail

        assert main(["events", "doctor"]) == 0
        out_doc = capsys.readouterr().out
        assert "Event Doctor" in out_doc


def test_events_list_json_contract(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = _config(tmp_path)
    config.ensure_dirs()
    logger = EventLogger(config.events_dir)
    _seed_run(logger)

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["events", "list", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["command"] == "atlas events list"
    assert payload["data"]["count"] >= 1


def test_events_doctor_fails_on_unknown_event_type(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = _config(tmp_path)
    config.ensure_dirs()
    bad_path = config.events_dir / "2026-01-01.jsonl"
    bad_event = {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "event_type": "unknown_type",
        "run_id": "x",
        "command": "atlas test",
        "mode": "paper",
        "payload": {},
    }
    bad_path.write_text(json.dumps(bad_event) + "\n", encoding="utf-8")

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["events", "doctor"]) == 2

    output = capsys.readouterr().out
    assert "unknown event_type" in output


def test_replay_last_and_replay_from_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = _config(tmp_path)
    config.ensure_dirs()
    logger = EventLogger(config.events_dir)
    _seed_run(logger, run_id="run-last")

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["replay", "--last"]) == 0
        out_last = capsys.readouterr().out
        assert "inputs/context" in out_last
        assert "market state" in out_last

        latest_file = sorted(config.events_dir.glob("*.jsonl"))[-1]
        assert main(["replay", str(latest_file)]) == 0
        out_file = capsys.readouterr().out
        assert "Source:" in out_file


def test_replay_without_events_is_safe(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = _config(tmp_path)
    config.ensure_dirs()

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["replay", "--last"]) == 0

    output = capsys.readouterr().out
    assert "No replay data available yet" in output
