# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/research/test_research_backtest_proposal_cli.py
# PURPOSE: Verifies the `atlas research backtest-proposal` command reports what
#         the bridge derived and claims no execution authority.
# DEPS:    json, pathlib, unittest, pytest, atlas_agent.
# ==============================================================================

"""CLI tests for the research-to-backtest proposal command.

Read-only and offline: no provider call, no broker call, no order, no approval.
"""

# --- IMPORTS ---

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
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
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending_orders",
        reports_dir=tmp_path / "reports",
        events_dir=tmp_path / "events",
        data_path=tmp_path / "data" / "ohlcv.csv",
        workspace_root=tmp_path,
    )


def _create_artifact(
    tmp_path: Path,
    monkeypatch,
    *,
    symbol: str = "AAPL",
    hypothesis: dict[str, Any] | None = None,
) -> str:
    """Create a real research artifact, then attach a hypothesis to it."""
    from atlas_agent.research.session import run_research_session

    (tmp_path / "memory").mkdir(exist_ok=True)
    monkeypatch.chdir(tmp_path)
    artifact = run_research_session(
        symbol=symbol,
        workspace_path=tmp_path,
        memory_dir=None,
        event_logger=None,
        provider_name="deterministic",
    )
    if hypothesis is not None:
        path = tmp_path / artifact.artifact_path
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.setdefault("metadata", {})["backtest_hypothesis"] = hypothesis
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return artifact.run_id


class TestBacktestProposalText:
    def test_accepted_strategy_is_reported(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_artifact(
            tmp_path,
            monkeypatch,
            hypothesis={
                "strategies": ["moving_average_cross"],
                "parameters": {"moving_average_cross": {"short_window": 3, "long_window": 8}},
            },
        )
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "backtest-proposal", run_id]) == 0

        out = capsys.readouterr().out
        assert "Backtest proposal" in out
        assert "Symbol: AAPL" in out
        assert "Mode: paper" in out
        assert "Status: proposed" in out
        assert "moving_average_cross" in out
        assert "short_window=3" in out
        assert "not financial advice" in out.lower()

    def test_artifact_without_hypothesis_reports_absence(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        run_id = _create_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "backtest-proposal", run_id]) == 0

        out = capsys.readouterr().out
        assert "Status: no_hypothesis" in out
        assert "Accepted strategies: 0" in out

    def test_rejections_are_shown_with_their_reason(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        run_id = _create_artifact(
            tmp_path,
            monkeypatch,
            hypothesis={"strategies": ["definitely_not_registered"]},
        )
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "backtest-proposal", run_id]) == 0

        out = capsys.readouterr().out
        assert "definitely_not_registered" in out
        assert "not registered" in out


class TestBacktestProposalJson:
    def test_json_envelope_carries_the_proposal(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        run_id = _create_artifact(
            tmp_path,
            monkeypatch,
            hypothesis={"strategies": ["buy_and_hold"]},
        )
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "backtest-proposal", run_id, "--json"]) == 0

        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["ok"] is True
        assert payload["status"] == "backtest_proposal_built"
        proposal = payload["proposal"]
        assert proposal["symbol"] == "AAPL"
        assert proposal["mode"] == "paper"
        assert proposal["source_run_id"] == run_id
        assert [item["strategy_id"] for item in proposal["accepted_strategies"]] == [
            "buy_and_hold"
        ]
        safety = proposal["safety"]
        assert safety["creates_pending_orders"] is False
        assert safety["creates_approvals"] is False
        assert safety["submits_broker_orders"] is False
        assert safety["network_required"] is False

    def test_missing_artifact_returns_safe_error(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        (tmp_path / "memory").mkdir(exist_ok=True)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "backtest-proposal", "run-missing", "--json"]) == 1

        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["ok"] is False
        assert payload["status"] == "research_artifact_not_found"

    def test_unsafe_run_id_is_rejected(self, tmp_path: Path, capsys, monkeypatch) -> None:
        (tmp_path / "memory").mkdir(exist_ok=True)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "backtest-proposal", "../escape", "--json"]) == 1

        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["ok"] is False
        assert payload["status"] == "invalid_research_id"


class TestBacktestProposalSideEffects:
    def test_command_creates_no_pending_orders(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        run_id = _create_artifact(
            tmp_path,
            monkeypatch,
            hypothesis={"strategies": ["buy_and_hold"]},
        )
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "backtest-proposal", run_id]) == 0

        assert list((tmp_path / "pending_orders").glob("*.json")) == []

    def test_command_does_not_modify_the_source_artifact(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        run_id = _create_artifact(
            tmp_path,
            monkeypatch,
            hypothesis={"strategies": ["buy_and_hold"]},
        )
        artifact_path = next((tmp_path / ".atlas" / "research").rglob(f"{run_id}.json"))
        before = artifact_path.read_bytes()

        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "backtest-proposal", run_id]) == 0

        assert artifact_path.read_bytes() == before
