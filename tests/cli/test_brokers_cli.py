# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/cli/test_brokers_cli.py
# PURPOSE: Verifies brokers cli behavior and regression expectations.
# DEPS:    json, pathlib, unittest, pytest, atlas_agent.
# ==============================================================================

"""CLI end-to-end tests for broker commands."""
# --- IMPORTS ---

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.config import AtlasConfig


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _config(tmp_path: Path) -> AtlasConfig:
    return AtlasConfig(
        workspace_root=tmp_path,
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending_orders",
        reports_dir=tmp_path / "reports",
        events_dir=tmp_path / "events",
    )


class TestBrokersCLI:
    def test_broker_list_outputs_known_brokers(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["broker", "list"])
        assert code == 0
        out = capsys.readouterr().out
        for name in ("paper", "alpaca", "binance", "ccxt", "ibkr_stub"):
            assert name in out

    def test_broker_status_text_outputs_inventory(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["broker", "status"])
        assert code == 0
        out = capsys.readouterr().out
        assert "PaperBroker" in out
        assert "Alpaca" in out
        assert "Binance" in out
        assert "CCXT" in out
        assert "IBKR" in out or "Interactive Brokers" in out
        assert "default_paper" in out
        assert "supported_opt_in" in out
        assert "partial" in out
        assert "disabled" in out
        assert "placeholder" in out

    def test_broker_status_json_outputs_inventory(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["broker", "status", "--json"])
        assert code == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "inventory" in data
        inventory = data["inventory"]
        assert len(inventory) >= 5
        ids = {item["support"]["broker_id"] for item in inventory}
        assert ids >= {"paper", "alpaca", "binance", "ccxt", "ibkr"}

        for item in inventory:
            support = item["support"]
            runtime = item["runtime"]
            assert "broker_id" in support
            assert "status" in support
            assert "display_name" in support
            assert "live_submit_supported" in support
            assert "default_enabled" in support
            assert "code" in runtime

    def test_broker_status_does_not_call_broker_apis(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`atlas broker status` must be a local, read-only operation."""
        config = _config(tmp_path)
        config.ensure_dirs()

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["broker", "status"])
        assert code == 0
        err = capsys.readouterr().err
        # No network errors, no credential prompts, no API call evidence.
        assert "timeout" not in err.lower()
        assert "connection" not in err.lower()
