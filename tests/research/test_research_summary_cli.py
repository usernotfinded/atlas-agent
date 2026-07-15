# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/research/test_research_summary_cli.py
# PURPOSE: Verifies research summary cli behavior and regression expectations.
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


def _run_research(tmp_path: Path, monkeypatch, capsys, symbol: str) -> str:
    config = _config(tmp_path)
    config.ensure_dirs()
    monkeypatch.chdir(tmp_path)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        main(["research", "run", "--symbol", symbol, "--json"])
    out = json.loads(capsys.readouterr().out.strip())
    return out["run_id"]


def _run_plan(tmp_path: Path, monkeypatch, capsys, run_id: str) -> str:
    config = _config(tmp_path)
    config.ensure_dirs()
    monkeypatch.chdir(tmp_path)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        main(["research", "plan", run_id, "--json"])
    out = json.loads(capsys.readouterr().out.strip())
    return out["plan_id"]


class TestResearchSummaryNoArtifacts:
    def test_summary_no_artifacts_text(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "summary"]) == 0
        out = capsys.readouterr().out
        assert "No research artifacts found" in out

    def test_summary_no_artifacts_json(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "summary", "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        assert data["status"] == "research_summary"
        assert data["research_count"] == 0
        assert data["plan_count"] == 0
        assert data["symbols"] == []


class TestResearchSummaryAfterRun:
    def test_summary_includes_research(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "summary"]) == 0
        out = capsys.readouterr().out
        assert "AAPL" in out
        assert run_id in out
        assert "/Users/" not in out
        assert "/private/var/" not in out


class TestResearchSummaryAfterPlan:
    def test_summary_includes_plan(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "summary"]) == 0
        out = capsys.readouterr().out
        assert "Research artifacts: 1" in out
        assert "Paper plans: 1" in out
        assert plan_id in out


class TestResearchSummaryJson:
    def test_json_shape(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        _run_plan(tmp_path, monkeypatch, capsys, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "summary", "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        assert data["status"] == "research_summary"
        assert data["research_count"] == 1
        assert data["plan_count"] == 1
        assert isinstance(data["symbols"], list)
        assert len(data["symbols"]) == 1
        sym = data["symbols"][0]
        assert sym["symbol"] == "AAPL"
        assert sym["research_count"] == 1
        assert sym["plan_count"] == 1
        assert sym["latest_research_run_id"] == run_id
        assert sym["latest_plan_id"] is not None
        assert sym["latest_research_path"].startswith(".atlas/research/")
        assert sym["latest_plan_path"].startswith(".atlas/research/")
        assert "/Users/" not in out
        assert "/private/var/" not in out

    def test_json_no_secrets(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "summary", "--json"])
        out = capsys.readouterr().out.strip()
        assert "sk-" not in out.lower()
        assert "pplx-" not in out.lower()


class TestResearchSummaryMultipleSymbols:
    def test_multiple_symbols_sorted(self, tmp_path: Path, capsys, monkeypatch) -> None:
        _run_research(tmp_path, monkeypatch, capsys, "MSFT")
        _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "summary", "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        symbols = [s["symbol"] for s in data["symbols"]]
        assert symbols == ["AAPL", "MSFT"]


class TestResearchSummaryMalformed:
    def test_malformed_does_not_crash(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        bad_dir = tmp_path / ".atlas" / "research" / "AAPL"
        bad_dir.mkdir(parents=True)
        (bad_dir / "bad.json").write_text("not json", encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "summary"]) == 0
        out = capsys.readouterr().out
        assert "malformed" in out.lower() or "Warning" in out
        assert "not json" not in out

    def test_malformed_json_has_warning(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        bad_dir = tmp_path / ".atlas" / "research" / "AAPL"
        bad_dir.mkdir(parents=True)
        (bad_dir / "bad.json").write_text("not json", encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "summary", "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        assert len(data["warnings"]) >= 1


class TestResearchSummarySymlink:
    def test_ignores_symlink_outside_workspace(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        outside = tmp_path.parent / "outside.json"
        outside.write_text(
            json.dumps({
                "run_id": "x", "symbol": "OUT", "created_at": "2026-01-01T00:00:00+00:00",
                "mode": "paper", "provider": "det", "summary": "s", "thesis": "t",
                "market_context": "m", "risks": [], "invalidation_conditions": [],
                "paper_only_plan": "p", "memory_hits": [], "citations": [],
                "warnings": [], "artifact_path": "", "metadata": {},
            }),
            encoding="utf-8",
        )
        research_dir = tmp_path / ".atlas" / "research" / "OUT"
        research_dir.mkdir(parents=True)
        (research_dir / "x.json").symlink_to(outside)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "summary"]) == 0
        out = capsys.readouterr().out
        assert "OUT" not in out


class TestResearchSummaryReadOnly:
    def test_no_new_artifacts(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        # Create one artifact first
        _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        research_count_before = len(list((tmp_path / ".atlas" / "research").rglob("*.json")))
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "summary"])
        research_count_after = len(list((tmp_path / ".atlas" / "research").rglob("*.json")))
        assert research_count_before == research_count_after

    def test_no_pending_orders(self, tmp_path: Path, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "summary"])
        pending = tmp_path / "pending_orders"
        assert not pending.exists() or not any(pending.iterdir())


class TestResearchSummaryNoExecutionPath:
    def test_no_broker_calls(self, tmp_path: Path, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config), \
             patch("atlas_agent.execution.order_router.OrderRouter.route") as mock_route, \
             patch("atlas_agent.execution.approval.ApprovalManager.create_pending_order") as mock_approval, \
             patch("atlas_agent.brokers.resolver.BrokerResolver.resolve_execution_broker") as mock_broker:
            main(["research", "summary"])
            mock_route.assert_not_called()
            mock_approval.assert_not_called()
            mock_broker.assert_not_called()


class TestResearchSummaryHelp:
    def test_help_exits_zero(self, capsys) -> None:
        assert main(["research", "summary", "--help"]) == 0
        out = capsys.readouterr().out
        assert "summary" in out.lower()
        assert "read-only" in out.lower() or "read only" in out.lower()
