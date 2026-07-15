# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/research/test_research_verify_cli.py
# PURPOSE: Verifies research verify cli behavior and regression expectations.
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


class TestResearchVerifyCreatesArtifact:
    def test_verify_creates_artifact(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "verify", plan_id]) == 0
        out = capsys.readouterr().out
        assert "Paper plan verification created" in out
        assert "Symbol: AAPL" in out
        assert f"Source Plan ID: {plan_id}" in out
        assert "Verification ID:" in out
        assert "Recommendation: paper_review_ready" in out
        assert ".atlas/research/AAPL/verifications/" in out

    def test_verify_artifact_json_valid(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "verify", plan_id, "--json"])
        out = json.loads(capsys.readouterr().out.strip())
        v_path = tmp_path / out["artifact_path"]
        assert v_path.exists()
        data = json.loads(v_path.read_text())
        assert data["mode"] == "paper"
        assert data["source_plan_id"] == plan_id
        assert data["symbol"] == "AAPL"
        assert "verification_id" in data
        assert "checks" in data
        assert data["recommendation"] == "paper_review_ready"
        assert data["passed_checks"] > 0
        assert data["failed_checks"] == 0


class TestResearchVerifyJsonOutput:
    def test_json_output_shape(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "verify", plan_id, "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        assert data["status"] == "research_verification_created"
        assert data["symbol"] == "AAPL"
        assert data["source_plan_id"] == plan_id
        assert "verification_id" in data
        assert "recommendation" in data
        assert "artifact_path" in data
        assert "passed_checks" in data
        assert "failed_checks" in data
        assert not data["artifact_path"].startswith("/")
        assert "/Users/" not in data["artifact_path"]
        assert "/private/var/" not in data["artifact_path"]

    def test_json_no_secrets(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "verify", plan_id, "--json"])
        out = capsys.readouterr().out.strip()
        assert "sk-" not in out.lower()
        assert "pplx-" not in out.lower()


class TestResearchVerifyTextOutput:
    def test_text_output_shape(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "verify", plan_id]) == 0
        out = capsys.readouterr().out
        assert "Paper plan verification created" in out
        assert "Symbol:" in out
        assert "Source Plan ID:" in out
        assert "Verification ID:" in out
        assert "Recommendation:" in out
        assert "Artifact:" in out

    def test_text_no_absolute_paths(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "verify", plan_id])
        out = capsys.readouterr().out
        assert "/Users/" not in out
        assert "/private/var/" not in out


class TestResearchVerifyNotFound:
    def test_not_found_text(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "verify", "missing-id"])
        assert code == 1
        out = capsys.readouterr().out
        assert "not found" in out.lower() or "research verify skipped safely" in out.lower()

    def test_not_found_json(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "verify", "missing-id", "--json"])
        assert code == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert "status" in data


class TestResearchVerifyInvalidPlanId:
    def test_invalid_plan_id_text(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "verify", "../secret"])
        assert code == 1
        out = capsys.readouterr().out
        assert "unsafe" in out.lower() or "research verify skipped safely" in out.lower()

    def test_invalid_plan_id_json(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "verify", "../secret", "--json"])
        assert code == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False


class TestResearchVerifyAmbiguous:
    def test_ambiguous_plan_id(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        research_dir = tmp_path / ".atlas" / "research"
        for sym in ("AAPL", "MSFT"):
            plans_dir = research_dir / sym / "plans"
            plans_dir.mkdir(parents=True)
            plan_data = {
                "plan_id": "sharedplanid",
                "source_run_id": "run1",
                "symbol": sym,
                "created_at": "2026-01-01T00:00:00+00:00",
                "mode": "paper",
                "provider": "deterministic",
                "source_artifact_path": ".atlas/research/AAPL/run1.json",
                "thesis_recap": "t",
                "constraints": ["paper-only"],
                "risk_notes": ["r"],
                "invalidation_checks": ["i"],
                "paper_only_actions": ["a"],
                "verification_steps": ["v"],
                "warnings": [],
                "artifact_path": "",
                "metadata": {},
            }
            (plans_dir / "sharedplanid.json").write_text(
                json.dumps(plan_data), encoding="utf-8"
            )
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "verify", "sharedplanid"])
        assert code == 1
        out = capsys.readouterr().out
        assert "invalid research identifier" in out.lower()


class TestResearchVerifyMalformedSource:
    def test_malformed_source_plan(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        plans_dir = tmp_path / ".atlas" / "research" / "AAPL" / "plans"
        plans_dir.mkdir(parents=True)
        (plans_dir / "validplanid.json").write_text("not json", encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "verify", "validplanid"])
        assert code == 1
        out = capsys.readouterr().out
        assert "malformed" in out.lower() or "research verify skipped safely" in out.lower()


class TestResearchVerifyUnsupportedProvider:
    def test_unsupported_provider_text(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "verify", plan_id, "--provider", "openai"])
        assert code == 1
        out = capsys.readouterr().out
        assert "unsupported research provider" in out.lower()
        assert "openai" not in out.lower()

    def test_unsupported_provider_no_artifact(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "verify", plan_id, "--provider", "openai"])
        verifications_dir = tmp_path / ".atlas" / "research" / "AAPL" / "verifications"
        assert not verifications_dir.exists() or not any(verifications_dir.glob("*.json"))


class TestResearchVerifyFailedChecks:
    def test_missing_risk_notes(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        plans_dir = tmp_path / ".atlas" / "research" / "AAPL" / "plans"
        plans_dir.mkdir(parents=True)
        plan_data = {
            "plan_id": "plan1",
            "source_run_id": "run1",
            "symbol": "AAPL",
            "created_at": "2026-01-01T00:00:00+00:00",
            "mode": "paper",
            "provider": "deterministic",
            "source_artifact_path": ".atlas/research/AAPL/run1.json",
            "thesis_recap": "t",
            "constraints": ["paper-only"],
            "risk_notes": [],
            "invalidation_checks": ["i"],
            "paper_only_actions": ["a"],
            "verification_steps": ["v"],
            "warnings": [],
            "artifact_path": "",
            "metadata": {},
        }
        (plans_dir / "plan1.json").write_text(json.dumps(plan_data), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "verify", "plan1", "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        assert data["recommendation"] == "manual_review_required"
        assert data["failed_checks"] > 0

    def test_dangerous_language(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        plans_dir = tmp_path / ".atlas" / "research" / "AAPL" / "plans"
        plans_dir.mkdir(parents=True)
        plan_data = {
            "plan_id": "plan2",
            "source_run_id": "run1",
            "symbol": "AAPL",
            "created_at": "2026-01-01T00:00:00+00:00",
            "mode": "paper",
            "provider": "deterministic",
            "source_artifact_path": ".atlas/research/AAPL/run1.json",
            "thesis_recap": "submit live order now",
            "constraints": ["paper-only"],
            "risk_notes": ["r"],
            "invalidation_checks": ["i"],
            "paper_only_actions": ["a"],
            "verification_steps": ["v"],
            "warnings": [],
            "artifact_path": "",
            "metadata": {},
        }
        (plans_dir / "plan2.json").write_text(json.dumps(plan_data), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "verify", "plan2", "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        assert data["recommendation"] == "manual_review_required"
        assert data["failed_checks"] > 0
        # Dangerous phrase must not leak into output
        assert "submit live order" not in out.lower()


class TestResearchVerifyEventSafety:
    def test_event_payload_safe(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "verify", plan_id])
        events_dir = tmp_path / "events"
        event_files = list(events_dir.glob("*.jsonl"))
        assert len(event_files) >= 1
        latest = event_files[-1]
        lines = latest.read_text().strip().splitlines()
        verify_event = None
        for line in lines:
            ev = json.loads(line)
            if ev.get("event_type") == "research_verification_created":
                verify_event = ev
                break
        assert verify_event is not None
        payload = verify_event["payload"]
        assert "verification_id" in payload
        assert "source_plan_id" in payload
        assert "source_run_id" in payload
        assert "symbol" in payload
        assert "recommendation" in payload
        assert "passed_checks" in payload
        assert "failed_checks" in payload
        assert "artifact_path" in payload
        # Must NOT contain full bodies
        assert "checks" not in payload
        assert "thesis_recap" not in payload
        assert "risk_notes" not in payload


class TestResearchVerifyNoExecutionPath:
    def test_no_broker_calls(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config), \
             patch("atlas_agent.execution.order_router.OrderRouter.route") as mock_route, \
             patch("atlas_agent.execution.approval.ApprovalManager.create_pending_order") as mock_approval, \
             patch("atlas_agent.brokers.resolver.BrokerResolver.resolve_execution_broker") as mock_broker:
            main(["research", "verify", plan_id])
            mock_route.assert_not_called()
            mock_approval.assert_not_called()
            mock_broker.assert_not_called()


class TestResearchVerifyNoPendingOrder:
    def test_no_pending_orders_created(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "verify", plan_id])
        pending = tmp_path / "pending_orders"
        assert not pending.exists() or not any(pending.iterdir())


class TestResearchVerifyNoBrokerCredentials:
    def test_works_without_broker_env(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "verify", plan_id]) == 0


class TestResearchVerifySymlink:
    def test_ignores_symlink_outside_workspace(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        outside = tmp_path.parent / "outside_plan.json"
        outside.write_text(
            json.dumps({
                "plan_id": "x", "source_run_id": "r", "symbol": "OUT",
                "created_at": "2026-01-01T00:00:00+00:00", "mode": "paper",
                "provider": "det", "source_artifact_path": "", "thesis_recap": "t",
                "constraints": ["paper-only"], "risk_notes": ["r"],
                "invalidation_checks": ["i"], "paper_only_actions": ["a"],
                "verification_steps": ["v"], "warnings": [],
                "artifact_path": "", "metadata": {},
            }),
            encoding="utf-8",
        )
        plans_dir = tmp_path / ".atlas" / "research" / "OUT" / "plans"
        plans_dir.mkdir(parents=True)
        (plans_dir / "x.json").symlink_to(outside)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "verify", "x"])
        assert code == 1
        out = capsys.readouterr().out
        assert "not found" in out.lower() or "skipped safely" in out.lower()


class TestResearchVerifyStableSchema:
    def test_required_keys_exist(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "verify", plan_id, "--json"])
        out = json.loads(capsys.readouterr().out.strip())
        v_path = tmp_path / out["artifact_path"]
        data = json.loads(v_path.read_text())
        required_keys = [
            "verification_id", "source_plan_id", "source_run_id",
            "symbol", "mode", "provider", "source_plan_path",
            "checks", "passed_checks", "failed_checks",
            "recommendation", "artifact_path", "metadata",
        ]
        for k in required_keys:
            assert k in data, f"Missing key: {k}"
        check_names = {c["name"] for c in data["checks"]}
        required_checks = [
            "plan_schema_complete", "paper_only_mode", "no_live_authorization_language",
            "has_risk_notes", "has_invalidation_checks", "has_verification_steps",
            "has_paper_only_constraints", "source_path_contained",
        ]
        for name in required_checks:
            assert name in check_names, f"Missing check: {name}"
        assert data["recommendation"] in ("paper_review_ready", "manual_review_required")

    def test_recommendation_values(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        plans_dir = tmp_path / ".atlas" / "research" / "AAPL" / "plans"
        plans_dir.mkdir(parents=True)
        # Good plan
        good = {
            "plan_id": "good", "source_run_id": "r", "symbol": "AAPL",
            "created_at": "2026-01-01T00:00:00+00:00", "mode": "paper",
            "provider": "deterministic", "source_artifact_path": ".atlas/research/AAPL/r.json",
            "thesis_recap": "t", "constraints": ["paper-only"],
            "risk_notes": ["r"], "invalidation_checks": ["i"],
            "paper_only_actions": ["a"], "verification_steps": ["v"],
            "warnings": [], "artifact_path": "", "metadata": {},
        }
        (plans_dir / "good.json").write_text(json.dumps(good), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "verify", "good", "--json"])
        out = json.loads(capsys.readouterr().out.strip())
        assert out["recommendation"] == "paper_review_ready"

        # Bad plan
        bad = {
            "plan_id": "bad", "source_run_id": "r", "symbol": "AAPL",
            "created_at": "2026-01-01T00:00:00+00:00", "mode": "live",
            "provider": "deterministic", "source_artifact_path": ".atlas/research/AAPL/r.json",
            "thesis_recap": "t", "constraints": [],
            "risk_notes": [], "invalidation_checks": [],
            "paper_only_actions": [], "verification_steps": [],
            "warnings": [], "artifact_path": "", "metadata": {},
        }
        (plans_dir / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "verify", "bad", "--json"])
        out = json.loads(capsys.readouterr().out.strip())
        assert out["recommendation"] == "manual_review_required"
