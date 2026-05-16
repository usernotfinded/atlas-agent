from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.config import AtlasConfig


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


def _create_research_artifact(tmp_path: Path, monkeypatch, symbol: str = "AAPL") -> str:
    from atlas_agent.research.session import run_research_session
    # Create workspace marker so resolve_workspace_path() works
    (tmp_path / "memory").mkdir(exist_ok=True)
    monkeypatch.chdir(tmp_path)
    artifact = run_research_session(
        symbol=symbol,
        workspace_path=tmp_path,
        memory_dir=None,
        event_logger=None,
        provider_name="deterministic",
    )
    return artifact.run_id


class TestResearchPlanCreatesArtifact:
    def test_plan_creates_artifact(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "plan", run_id]) == 0
        out = capsys.readouterr().out
        assert "Paper plan created" in out
        assert "Symbol: AAPL" in out
        assert f"Source Run ID: {run_id}" in out
        assert "Plan ID:" in out
        assert ".atlas/research/AAPL/plans/" in out

    def test_plan_artifact_json_valid(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "plan", run_id, "--json"])
        out = json.loads(capsys.readouterr().out.strip())
        plan_path = tmp_path / out["artifact_path"]
        assert plan_path.exists()
        data = json.loads(plan_path.read_text())
        assert data["mode"] == "paper"
        assert data["source_run_id"] == run_id
        assert data["symbol"] == "AAPL"
        assert "plan_id" in data
        assert "thesis_recap" in data
        assert "constraints" in data
        assert "risk_notes" in data
        assert "invalidation_checks" in data
        assert "paper_only_actions" in data
        assert "verification_steps" in data
        assert "metadata" in data

    def test_plan_constraints_include_paper_only(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "plan", run_id])
        plan_dir = tmp_path / ".atlas" / "research" / "AAPL" / "plans"
        plan_files = list(plan_dir.glob("*.json"))
        assert len(plan_files) == 1
        data = json.loads(plan_files[0].read_text())
        constraints_lower = " ".join(data["constraints"]).lower()
        assert "paper-only" in constraints_lower
        assert "does not authorize live trading" in constraints_lower
        assert "does not create pending orders" in constraints_lower

    def test_plan_paper_only_actions_no_live_submit(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "plan", run_id])
        plan_dir = tmp_path / ".atlas" / "research" / "AAPL" / "plans"
        plan_files = list(plan_dir.glob("*.json"))
        data = json.loads(plan_files[0].read_text())
        actions_lower = " ".join(data["paper_only_actions"]).lower()
        assert "live-submit" not in actions_lower
        assert "authorization" not in actions_lower


class TestResearchPlanJsonOutput:
    def test_json_output_shape(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "plan", run_id, "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        assert data["status"] == "paper_plan_created"
        assert data["symbol"] == "AAPL"
        assert data["source_run_id"] == run_id
        assert "plan_id" in data
        assert "artifact_path" in data
        assert "warnings" in data
        assert not data["artifact_path"].startswith("/")
        assert "/Users/" not in data["artifact_path"]
        assert "/private/var/" not in data["artifact_path"]

    def test_json_no_secrets(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "plan", run_id, "--json"])
        out = capsys.readouterr().out.strip()
        assert "sk-" not in out.lower()
        assert "pplx-" not in out.lower()


class TestResearchPlanTextOutput:
    def test_text_output_shape(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "plan", run_id]) == 0
        out = capsys.readouterr().out
        assert "Paper plan created" in out
        assert "Symbol:" in out
        assert "Source Run ID:" in out
        assert "Plan ID:" in out
        assert "Artifact:" in out

    def test_text_no_absolute_paths(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "plan", run_id])
        out = capsys.readouterr().out
        assert "/Users/" not in out
        assert "/private/var/" not in out


class TestResearchPlanNotFound:
    def test_not_found_text(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "plan", "missing-id"])
        assert code == 1
        out = capsys.readouterr().out
        assert "not found" in out.lower() or "research plan skipped safely" in out.lower()

    def test_not_found_json(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "plan", "missing-id", "--json"])
        assert code == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert "status" in data


class TestResearchPlanInvalidRunId:
    def test_invalid_run_id_text(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "plan", "../secret"])
        assert code == 1
        out = capsys.readouterr().out
        assert "unsafe" in out.lower() or "research plan skipped safely" in out.lower()

    def test_invalid_run_id_json(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "plan", "../secret", "--json"])
        assert code == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False


class TestResearchPlanAmbiguous:
    def test_ambiguous_run_id(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        research_dir = tmp_path / ".atlas" / "research"
        for sym in ("AAPL", "MSFT"):
            (research_dir / sym).mkdir(parents=True)
            artifact_data = {
                "run_id": "sharedrunid",
                "symbol": sym,
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
            (research_dir / sym / "sharedrunid.json").write_text(
                json.dumps(artifact_data), encoding="utf-8"
            )
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "plan", "sharedrunid"])
        assert code == 1
        out = capsys.readouterr().out
        assert "ambiguous" in out.lower()


class TestResearchPlanMalformedSource:
    def test_malformed_source_artifact(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        research_dir = tmp_path / ".atlas" / "research" / "AAPL"
        research_dir.mkdir(parents=True)
        (research_dir / "validrunid.json").write_text("not json", encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "plan", "validrunid"])
        assert code == 1
        out = capsys.readouterr().out
        assert "malformed" in out.lower() or "research plan skipped safely" in out.lower()


class TestResearchPlanUnsupportedProvider:
    def test_unsupported_provider_text(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "plan", run_id, "--provider", "openai"])
        assert code == 1
        out = capsys.readouterr().out
        assert "unsupported_research_provider" in out

    def test_unsupported_provider_no_artifact(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "plan", run_id, "--provider", "openai"])
        plans_dir = tmp_path / ".atlas" / "research" / "AAPL" / "plans"
        assert not plans_dir.exists() or not any(plans_dir.glob("*.json"))


class TestResearchPlanEventSafety:
    def test_event_payload_safe(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "plan", run_id])
        events_file = tmp_path / "events" / f"{tmp_path.name}.jsonl"
        # Events are written to events/YYYY-MM-DD.jsonl
        events_dir = tmp_path / "events"
        event_files = list(events_dir.glob("*.jsonl"))
        assert len(event_files) >= 1
        latest = event_files[-1]
        lines = latest.read_text().strip().splitlines()
        plan_event = None
        for line in lines:
            ev = json.loads(line)
            if ev.get("event_type") == "research_plan_created":
                plan_event = ev
                break
        assert plan_event is not None
        payload = plan_event["payload"]
        assert "plan_id" in payload
        assert "source_run_id" in payload
        assert "symbol" in payload
        assert "artifact_path" in payload
        assert "thesis_recap" not in payload
        assert "risk_notes" not in payload
        assert "paper_only_actions" not in payload


class TestResearchPlanNoExecutionPath:
    def test_no_broker_calls(self, tmp_path: Path, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config), \
             patch("atlas_agent.execution.order_router.OrderRouter.route") as mock_route, \
             patch("atlas_agent.execution.approval.ApprovalManager.create_pending_order") as mock_approval, \
             patch("atlas_agent.brokers.resolver.BrokerResolver.resolve_execution_broker") as mock_broker:
            main(["research", "plan", run_id])
            mock_route.assert_not_called()
            mock_approval.assert_not_called()
            mock_broker.assert_not_called()


class TestResearchPlanNoPendingOrder:
    def test_no_pending_orders_created(self, tmp_path: Path, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "plan", run_id])
        pending = tmp_path / "pending_orders"
        assert not pending.exists() or not any(pending.iterdir())


class TestResearchPlanNoBrokerCredentials:
    def test_works_without_broker_env(self, tmp_path: Path, monkeypatch) -> None:
        run_id = _create_research_artifact(tmp_path, monkeypatch)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "plan", run_id]) == 0


class TestResearchPlanSymlink:
    def test_ignores_symlink_outside_workspace(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        outside = tmp_path.parent / "outside.json"
        outside.write_text(json.dumps({"run_id": "x", "symbol": "OUT", "created_at": "2026-01-01T00:00:00+00:00", "mode": "paper", "provider": "det", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": "", "metadata": {}}), encoding="utf-8")
        research_dir = tmp_path / ".atlas" / "research" / "OUT"
        research_dir.mkdir(parents=True)
        (research_dir / "x.json").symlink_to(outside)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "plan", "x"])
        assert code == 1
        out = capsys.readouterr().out
        assert "not found" in out.lower() or "skipped safely" in out.lower()
