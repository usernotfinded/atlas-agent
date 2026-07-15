# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/research/test_research_cli_list_show.py
# PURPOSE: Verifies research cli list show behavior and regression expectations.
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


def _run_research(tmp_path: Path, monkeypatch, symbol: str) -> str:
    config = _config(tmp_path)
    config.ensure_dirs()
    monkeypatch.chdir(tmp_path)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        main(["research", "run", "--symbol", symbol, "--json"])
    out = json.loads(pytest.capsys.readouterr().out.strip())
    return out["run_id"]


class TestResearchListNoArtifacts:
    def test_list_no_artifacts_text(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "list"]) == 0
        out = capsys.readouterr().out
        assert "No research artifacts found" in out

    def test_list_no_artifacts_json(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "list", "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        assert data["status"] == "research_listed"
        assert data["items"] == []


class TestResearchListAfterRun:
    def test_list_includes_artifact(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "run", "--symbol", "AAPL", "--json"])
            capsys.readouterr()
            assert main(["research", "list"]) == 0
        out = capsys.readouterr().out
        assert "AAPL" in out
        assert ".atlas/research/AAPL/" in out

    def test_list_json_shape(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "run", "--symbol", "AAPL", "--json"])
            capsys.readouterr()
            assert main(["research", "list", "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        assert data["status"] == "research_listed"
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert "run_id" in item
        assert item["symbol"] == "AAPL"
        assert "created_at" in item
        assert "artifact_path" in item
        assert "provider" in item
        assert "warnings_count" in item
        assert not item["artifact_path"].startswith("/")
        assert "/Users/" not in item["artifact_path"]
        assert "/private/var/" not in item["artifact_path"]

    def test_list_relative_paths(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "run", "--symbol", "TSLA", "--json"])
            capsys.readouterr()
            assert main(["research", "list", "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["items"][0]["artifact_path"].startswith(".atlas/research/")


class TestResearchListSymbolFilter:
    def test_filter_by_symbol(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "run", "--symbol", "AAPL", "--json"])
            capsys.readouterr()
            main(["research", "run", "--symbol", "MSFT", "--json"])
            capsys.readouterr()
            assert main(["research", "list", "--symbol", "AAPL", "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert len(data["items"]) == 1
        assert data["items"][0]["symbol"] == "AAPL"


class TestResearchListLimit:
    def test_limit_respected(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            for sym in ("S1", "S2", "S3"):
                main(["research", "run", "--symbol", sym, "--json"])
                capsys.readouterr()
            assert main(["research", "list", "--limit", "2", "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert len(data["items"]) == 2

    def test_invalid_limit_clamped_or_safe(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "run", "--symbol", "AAPL", "--json"])
            capsys.readouterr()
            assert main(["research", "list", "--limit", "0", "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        # limit < 1 gets clamped to 1
        assert len(data["items"]) <= 1

    def test_huge_limit_clamped(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            for sym in ("S1", "S2", "S3"):
                main(["research", "run", "--symbol", sym, "--json"])
                capsys.readouterr()
            assert main(["research", "list", "--limit", "9999", "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert len(data["items"]) == 3


class TestResearchListMalformed:
    def test_list_ignores_malformed(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        bad_dir = tmp_path / ".atlas" / "research" / "AAPL"
        bad_dir.mkdir(parents=True)
        (bad_dir / "bad.json").write_text("not json", encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "list", "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True


class TestResearchShow:
    def test_show_by_run_id_text(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "run", "--symbol", "AAPL", "--json"])
            run_id = json.loads(capsys.readouterr().out.strip())["run_id"]
            assert main(["research", "show", run_id]) == 0
        out = capsys.readouterr().out
        assert "Research Artifact" in out
        assert f"Run ID: {run_id}" in out
        assert "Symbol: AAPL" in out
        assert "Summary:" in out
        assert "Thesis:" in out
        assert "Risks:" in out
        assert "Invalidation Conditions:" in out
        assert "Paper-only Plan:" in out
        assert "/Users/" not in out
        assert "/private/var/" not in out

    def test_show_by_run_id_json(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "run", "--symbol", "AAPL", "--json"])
            run_id = json.loads(capsys.readouterr().out.strip())["run_id"]
            assert main(["research", "show", run_id, "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        assert data["status"] == "research_loaded"
        artifact = data["artifact"]
        assert artifact["run_id"] == run_id
        assert artifact["symbol"] == "AAPL"
        assert "thesis" in artifact
        assert "risks" in artifact
        assert "invalidation_conditions" in artifact
        assert "paper_only_plan" in artifact
        assert not artifact["artifact_path"].startswith("/")

    def test_show_not_found(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "show", "missing-id"])
        assert code == 1
        out = capsys.readouterr().out
        assert "not found" in out.lower()

    def test_show_not_found_json(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "show", "missing-id", "--json"])
        assert code == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert data["status"] == "artifact_not_found"

    def test_show_invalid_run_id(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "show", "../secret"])
        assert code == 1
        out = capsys.readouterr().out
        assert "unsafe" in out.lower() or "research show skipped safely" in out.lower()

    def test_show_invalid_run_id_json(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "show", "../secret", "--json"])
        assert code == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert "status" in data

    def test_show_ambiguous_run_id(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        # Manually create two artifacts with same run_id under different symbols
        research_dir = tmp_path / ".atlas" / "research"
        (research_dir / "AAPL").mkdir(parents=True)
        (research_dir / "MSFT").mkdir(parents=True)
        shared_run_id = "abc123"
        artifact_data = {
            "run_id": shared_run_id,
            "symbol": "AAPL",
            "created_at": "2026-01-01T00:00:00+00:00",
            "mode": "paper",
            "provider": "deterministic",
            "summary": "s",
            "thesis": "t",
            "market_context": "m",
            "risks": [],
            "invalidation_conditions": [],
            "paper_only_plan": "p",
            "memory_hits": [],
            "citations": [],
            "warnings": [],
            "artifact_path": "",
            "metadata": {},
        }
        (research_dir / "AAPL" / f"{shared_run_id}.json").write_text(
            json.dumps(artifact_data), encoding="utf-8"
        )
        artifact_data["symbol"] = "MSFT"
        (research_dir / "MSFT" / f"{shared_run_id}.json").write_text(
            json.dumps(artifact_data), encoding="utf-8"
        )
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "show", shared_run_id])
        assert code == 1
        out = capsys.readouterr().out
        assert "invalid research identifier" in out.lower()

    def test_show_malformed_artifact(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        research_dir = tmp_path / ".atlas" / "research" / "AAPL"
        research_dir.mkdir(parents=True)
        run_id = "validrunid"
        (research_dir / f"{run_id}.json").write_text("not json", encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "show", run_id])
        assert code == 1
        out = capsys.readouterr().out
        assert "malformed" in out.lower() or "research show skipped safely" in out.lower()


class TestResearchListShowReadOnly:
    def test_list_no_new_files(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "list"])
        assert not (tmp_path / "pending_orders").exists() or not any((tmp_path / "pending_orders").iterdir())

    def test_show_no_new_files(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "show", "missing"])
        assert not (tmp_path / "pending_orders").exists() or not any((tmp_path / "pending_orders").iterdir())


class TestResearchListShowNoExecutionPath:
    def test_list_no_broker_calls(self, tmp_path: Path, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config), \
             patch("atlas_agent.execution.order_router.OrderRouter.route") as mock_route, \
             patch("atlas_agent.execution.approval.ApprovalManager.create_pending_order") as mock_approval, \
             patch("atlas_agent.brokers.resolver.BrokerResolver.resolve_execution_broker") as mock_broker:
            main(["research", "list"])
            mock_route.assert_not_called()
            mock_approval.assert_not_called()
            mock_broker.assert_not_called()

    def test_show_no_broker_calls(self, tmp_path: Path, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config), \
             patch("atlas_agent.execution.order_router.OrderRouter.route") as mock_route, \
             patch("atlas_agent.execution.approval.ApprovalManager.create_pending_order") as mock_approval, \
             patch("atlas_agent.brokers.resolver.BrokerResolver.resolve_execution_broker") as mock_broker:
            main(["research", "show", "missing"])
            mock_route.assert_not_called()
            mock_approval.assert_not_called()
            mock_broker.assert_not_called()


class TestResearchListShowSymlink:
    def test_list_ignores_symlink_outside_workspace(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        outside = tmp_path.parent / "outside_artifact.json"
        outside.write_text(json.dumps({"run_id": "x", "symbol": "OUT", "created_at": "2026-01-01T00:00:00+00:00", "mode": "paper", "provider": "det", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": "", "metadata": {}}), encoding="utf-8")
        research_dir = tmp_path / ".atlas" / "research" / "OUT"
        research_dir.mkdir(parents=True)
        (research_dir / "x.json").symlink_to(outside)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "list", "--json"])
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        # Symlink outside workspace should be ignored
        assert all(item["symbol"] != "OUT" for item in data["items"])
