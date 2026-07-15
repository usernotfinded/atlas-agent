# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/research/test_research_cli.py
# PURPOSE: Verifies research cli behavior and regression expectations.
# DEPS:    json, subprocess, sys, pathlib, unittest, pytest, additional local
#         modules.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
import subprocess
import sys
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


class TestResearchHelp:
    def test_research_help_exits_zero(self, capsys) -> None:
        assert main(["research", "--help"]) == 0
        out = capsys.readouterr().out
        assert "paper-only" in out.lower()
        assert "analysis-only" in out.lower() or "artifact" in out.lower()

    def test_research_run_help_exits_zero(self, capsys) -> None:
        assert main(["research", "run", "--help"]) == 0
        out = capsys.readouterr().out
        assert "symbol" in out.lower()
        assert "json" in out.lower()
        assert "provider" in out.lower()

    def test_research_help_no_misleading_terms(self, capsys) -> None:
        main(["research", "--help"])
        out = capsys.readouterr().out.lower()
        assert "guaranteed" not in out
        assert "profit" not in out
        assert "safe live trading" not in out


class TestResearchRunJson:
    def test_json_output_shape(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "run", "--symbol", "AAPL", "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        assert data["status"] == "created"
        assert data["symbol"] == "AAPL"
        assert "run_id" in data
        assert "artifact_path" in data
        assert "warnings" in data
        assert data["mode"] == "paper"
        assert data["provider"] == "deterministic"

    def test_json_artifact_path_relative(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "run", "--symbol", "AAPL", "--json"])
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert not data["artifact_path"].startswith("/")
        assert "/Users/" not in data["artifact_path"]
        assert "/private/var/" not in data["artifact_path"]

    def test_json_no_secrets(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "run", "--symbol", "AAPL", "--json"])
        out = capsys.readouterr().out.strip()
        assert "sk-" not in out.lower()
        assert "pplx-" not in out.lower()
        assert "bearer " not in out.lower()


class TestResearchRunText:
    def test_text_output_shape(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "run", "--symbol", "AAPL"]) == 0
        out = capsys.readouterr().out
        assert "Research artifact created" in out
        assert "Symbol: AAPL" in out
        assert "Mode: paper" in out
        assert "Artifact:" in out

    def test_text_no_absolute_paths(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "run", "--symbol", "AAPL"])
        out = capsys.readouterr().out
        assert "/Users/" not in out
        assert "/private/var/" not in out

    def test_text_no_raw_json_body(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "run", "--symbol", "AAPL"])
        out = capsys.readouterr().out
        assert '"summary"' not in out
        assert '"thesis"' not in out


class TestResearchRunUnsupportedProvider:
    def test_unsupported_provider_text(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "run", "--symbol", "AAPL", "--provider", "openai"])
        assert code == 1
        out = capsys.readouterr().out
        assert "unsupported research provider" in out.lower()
        assert "openai" not in out.lower()

    def test_unsupported_provider_json(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "run", "--symbol", "AAPL", "--provider", "openai", "--json"])
        assert code == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert data["status"] == "unsupported_research_provider"

    def test_unsupported_provider_no_artifact(self, tmp_path: Path, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "run", "--symbol", "AAPL", "--provider", "openai"])
        research_dir = tmp_path / ".atlas" / "research"
        assert not research_dir.exists() or not any(research_dir.rglob("*.json"))


class TestResearchRunSymbolValidation:
    def test_slash_rejected(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "run", "--symbol", "foo/bar"])
        assert code == 1
        out = capsys.readouterr().out
        assert "invalid research symbol" in out.lower()
        assert "foo" not in out
        assert "/" not in out

    def test_backslash_rejected(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "run", "--symbol", "foo\\\\bar"])
        assert code == 1
        out = capsys.readouterr().out
        assert "invalid research symbol" in out.lower()
        assert "foo" not in out
        assert "\\" not in out

    def test_dotdot_rejected(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "run", "--symbol", "../etc/passwd"])
        assert code == 1
        out = capsys.readouterr().out
        assert "invalid research symbol" in out.lower()
        assert "etc" not in out
        assert "passwd" not in out

    def test_no_artifact_outside_workspace(self, tmp_path: Path, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "run", "--symbol", "../foo"])
        research_dir = tmp_path / ".atlas" / "research"
        # Should not create files outside workspace
        parent_dir = tmp_path.parent
        assert not (parent_dir / "foo.json").exists()


class TestResearchRunNoMemory:
    def test_no_memory_flag_skips_lookup(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        config.memory_dir.mkdir(parents=True, exist_ok=True)
        (config.memory_dir / "notes.md").write_text("AAPL looks interesting.")
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "run", "--symbol", "AAPL", "--no-memory", "--json"])
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        artifact_path = tmp_path / data["artifact_path"]
        artifact_data = json.loads(artifact_path.read_text())
        assert artifact_data["memory_hits"] == []


class TestResearchRunNoExecutionPath:
    def test_no_broker_calls(self, tmp_path: Path, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config), \
             patch("atlas_agent.execution.order_router.OrderRouter.route") as mock_route, \
             patch("atlas_agent.execution.approval.ApprovalManager.create_pending_order") as mock_approval, \
             patch("atlas_agent.brokers.resolver.BrokerResolver.resolve_execution_broker") as mock_broker:
            main(["research", "run", "--symbol", "AAPL", "--json"])
            mock_route.assert_not_called()
            mock_approval.assert_not_called()
            mock_broker.assert_not_called()
