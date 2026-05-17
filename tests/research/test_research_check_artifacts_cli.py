from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.config import AtlasConfig
from atlas_agent.research import RESEARCH_ARTIFACT_SCHEMA_VERSION


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


def _run_prompt(tmp_path: Path, monkeypatch, capsys, run_id: str) -> str:
    config = _config(tmp_path)
    monkeypatch.chdir(tmp_path)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        main(["research", "prompt", run_id, "--json"])
    out = json.loads(capsys.readouterr().out.strip())
    return out["prompt_packet_id"]


def _run_simulate(tmp_path: Path, monkeypatch, capsys, prompt_id: str) -> str:
    config = _config(tmp_path)
    monkeypatch.chdir(tmp_path)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        main(["research", "simulate-provider", prompt_id, "--json"])
    out = json.loads(capsys.readouterr().out.strip())
    return out["provider_response_id"]


def _run_review(tmp_path: Path, monkeypatch, capsys, response_id: str) -> str:
    config = _config(tmp_path)
    monkeypatch.chdir(tmp_path)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        main(["research", "review-response", response_id, "--json"])
    out = json.loads(capsys.readouterr().out.strip())
    return out["response_review_id"]


def _run_dossier(tmp_path: Path, monkeypatch, capsys, run_id: str) -> str:
    config = _config(tmp_path)
    monkeypatch.chdir(tmp_path)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        main(["research", "dossier", run_id, "--json"])
    out = json.loads(capsys.readouterr().out.strip())
    return out["dossier_id"]


def _default_csv(tmp_path: Path) -> Path:
    import csv

    path = tmp_path / "data" / "ohlcv.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"date": "2026-01-01", "open": "100", "high": "105", "low": "99", "close": "102", "volume": "1000"},
        {"date": "2026-01-02", "open": "102", "high": "106", "low": "101", "close": "104", "volume": "1200"},
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


class TestCheckArtifactsEmpty:
    def test_empty_workspace(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "check-artifacts"]) == 0
        out = capsys.readouterr().out
        assert "Research artifact health check" in out
        assert "No artifact health issues found." in out

    def test_empty_workspace_json(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "check-artifacts", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is True
        assert out["status"] == "research_artifacts_checked"
        assert out["counts"]["research"] == 0
        assert out["counts"]["plans"] == 0
        assert out["counts"]["verifications"] == 0
        assert out["counts"]["evaluations"] == 0
        assert out["issues"] == []
        assert out["warnings"] == []


class TestCheckArtifactsHappyPath:
    def test_full_chain_counts(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        csv_path = _default_csv(tmp_path)
        prompt_id = _run_prompt(tmp_path, monkeypatch, capsys, run_id)
        response_id = _run_simulate(tmp_path, monkeypatch, capsys, prompt_id)
        _run_review(tmp_path, monkeypatch, capsys, response_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "verify", plan_id, "--json"])
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "evaluate", plan_id, "--data", str(csv_path), "--json"])
        capsys.readouterr()  # clear capture
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "check-artifacts", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is True
        assert out["counts"]["research"] == 1
        assert out["counts"]["plans"] == 1
        assert out["counts"]["verifications"] == 1
        assert out["counts"]["evaluations"] == 1
        assert out["counts"]["prompts"] == 1
        assert out["counts"]["provider_responses"] == 1
        assert out["counts"]["response_reviews"] == 1
        assert out["counts"]["dossiers"] == 0
        assert out["issues"] == []
        assert out["warnings"] == []

    def test_full_chain_with_dossier_counts(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        csv_path = _default_csv(tmp_path)
        prompt_id = _run_prompt(tmp_path, monkeypatch, capsys, run_id)
        response_id = _run_simulate(tmp_path, monkeypatch, capsys, prompt_id)
        _run_review(tmp_path, monkeypatch, capsys, response_id)
        _run_dossier(tmp_path, monkeypatch, capsys, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "verify", plan_id, "--json"])
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "evaluate", plan_id, "--data", str(csv_path), "--json"])
        capsys.readouterr()  # clear capture
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "check-artifacts", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is True
        assert out["counts"]["research"] == 1
        assert out["counts"]["plans"] == 1
        assert out["counts"]["verifications"] == 1
        assert out["counts"]["evaluations"] == 1
        assert out["counts"]["prompts"] == 1
        assert out["counts"]["provider_responses"] == 1
        assert out["counts"]["response_reviews"] == 1
        assert out["counts"]["dossiers"] == 1
        assert out["issues"] == []
        assert out["warnings"] == []


class TestCheckArtifactsJsonShape:
    def test_json_no_absolute_paths(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "check-artifacts", "--json"])
        out = capsys.readouterr().out.strip()
        assert "/Users/" not in out
        assert "/private/var/" not in out


class TestCheckArtifactsStrict:
    def test_strict_exits_2_with_issue(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        bad_dir = tmp_path / ".atlas" / "research" / "AAPL"
        bad_dir.mkdir(parents=True)
        (bad_dir / "bad.json").write_text("not json", encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "check-artifacts", "--strict"])
        assert code == 2
        out = capsys.readouterr().out
        assert "malformed_json" in out

    def test_default_exits_0_with_issue(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        bad_dir = tmp_path / ".atlas" / "research" / "AAPL"
        bad_dir.mkdir(parents=True)
        (bad_dir / "bad.json").write_text("not json", encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "check-artifacts"])
        assert code == 0
        out = capsys.readouterr().out
        assert "malformed_json" in out


class TestCheckArtifactsUnsupportedSchema:
    def test_unsupported_schema_detected(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        artifact_dir = tmp_path / ".atlas" / "research" / "AAPL"
        artifact_dir.mkdir(parents=True)
        artifact = {
            "run_id": "badrunid",
            "symbol": "AAPL",
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
            "artifact_path": ".atlas/research/AAPL/badrunid.json",
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
            "schema_version": "999",
        }
        (artifact_dir / "badrunid.json").write_text(json.dumps(artifact), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "check-artifacts", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        codes = {i["code"] for i in out["issues"]}
        assert "unsupported_schema_version" in codes


class TestCheckArtifactsLegacySchema:
    def test_legacy_schema_detected(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        artifact_dir = tmp_path / ".atlas" / "research" / "AAPL"
        artifact_dir.mkdir(parents=True)
        artifact = {
            "run_id": "legacyrunid",
            "symbol": "AAPL",
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
            "artifact_path": ".atlas/research/AAPL/legacyrunid.json",
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        (artifact_dir / "legacyrunid.json").write_text(json.dumps(artifact), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "check-artifacts", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        codes = {w["code"] for w in out["warnings"]}
        assert "legacy_schema_version" in codes


class TestCheckArtifactsDuplicateId:
    def test_duplicate_run_id_detected(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        artifact_dir = tmp_path / ".atlas" / "research" / "AAPL"
        artifact_dir.mkdir(parents=True)
        base = {
            "run_id": "duprunid",
            "symbol": "AAPL",
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
            "artifact_path": ".atlas/research/AAPL/duprunid.json",
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
            "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        }
        (artifact_dir / "a.json").write_text(json.dumps(base), encoding="utf-8")
        (artifact_dir / "b.json").write_text(json.dumps(base), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "check-artifacts", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        codes = {i["code"] for i in out["issues"]}
        assert "duplicate_id" in codes

    def test_duplicate_plan_id_detected(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        plans_dir = tmp_path / ".atlas" / "research" / "AAPL" / "plans"
        plans_dir.mkdir(parents=True)
        base = {
            "plan_id": "dupplanid",
            "source_run_id": "run1",
            "symbol": "AAPL",
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
            "artifact_path": ".atlas/research/AAPL/plans/dupplanid.json",
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
            "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        }
        (plans_dir / "a.json").write_text(json.dumps(base), encoding="utf-8")
        (plans_dir / "b.json").write_text(json.dumps(base), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "check-artifacts", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        codes = {i["code"] for i in out["issues"]}
        assert "duplicate_id" in codes

    def test_duplicate_response_review_id_detected(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        reviews_dir = tmp_path / ".atlas" / "research" / "AAPL" / "response_reviews"
        reviews_dir.mkdir(parents=True)
        base = {
            "response_review_id": "duplicate-review-id",
            "source_provider_response_id": "resp-a",
            "source_prompt_packet_id": "prompt-a",
            "source_run_id": "run-a",
            "symbol": "AAPL",
            "mode": "paper",
            "provider": "deterministic-review",
            "recommendation": "provider_response_review_ready",
            "artifact_path": ".atlas/research/AAPL/response_reviews/duplicate-review-id.json",
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
            "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        }
        (reviews_dir / "review-a.json").write_text(json.dumps(base), encoding="utf-8")
        (reviews_dir / "review-b.json").write_text(json.dumps(base), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "check-artifacts", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is True
        codes = {i["code"] for i in out["issues"]}
        assert "duplicate_id" in codes
        # Issue paths should be relative, not absolute
        for issue in out["issues"]:
            if issue["code"] == "duplicate_id":
                assert not issue["path"].startswith("/")
                assert "/Users/" not in issue["path"]
                assert "/private/var/" not in issue["path"]

    def test_duplicate_response_review_id_strict_exits_2(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        reviews_dir = tmp_path / ".atlas" / "research" / "AAPL" / "response_reviews"
        reviews_dir.mkdir(parents=True)
        base = {
            "response_review_id": "duplicate-review-id",
            "source_provider_response_id": "resp-a",
            "source_prompt_packet_id": "prompt-a",
            "source_run_id": "run-a",
            "symbol": "AAPL",
            "mode": "paper",
            "provider": "deterministic-review",
            "recommendation": "provider_response_review_ready",
            "artifact_path": ".atlas/research/AAPL/response_reviews/duplicate-review-id.json",
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
            "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        }
        (reviews_dir / "review-a.json").write_text(json.dumps(base), encoding="utf-8")
        (reviews_dir / "review-b.json").write_text(json.dumps(base), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "check-artifacts", "--strict", "--json"]) == 2
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is True
        codes = {i["code"] for i in out["issues"]}
        assert "duplicate_id" in codes


class TestCheckArtifactsSymbolMismatch:
    def test_symbol_mismatch_detected(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        artifact_dir = tmp_path / ".atlas" / "research" / "AAPL"
        artifact_dir.mkdir(parents=True)
        artifact = {
            "run_id": "mismatchid",
            "symbol": "MSFT",
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
            "artifact_path": ".atlas/research/AAPL/mismatchid.json",
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
            "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        }
        (artifact_dir / "mismatchid.json").write_text(json.dumps(artifact), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "check-artifacts", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        codes = {w["code"] for w in out["warnings"]}
        assert "symbol_mismatch" in codes


class TestCheckArtifactsMissingFields:
    def test_missing_required_id_detected(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        artifact_dir = tmp_path / ".atlas" / "research" / "AAPL"
        artifact_dir.mkdir(parents=True)
        artifact = {
            "symbol": "AAPL",
            "mode": "paper",
            "provider": "deterministic",
            "summary": "s",
            "artifact_path": ".atlas/research/AAPL/noid.json",
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
            "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        }
        (artifact_dir / "noid.json").write_text(json.dumps(artifact), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "check-artifacts", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        codes = {i["code"] for i in out["issues"]}
        assert "missing_required_id" in codes


class TestCheckArtifactsSymbolFilter:
    def test_symbol_filter(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        for sym in ("AAPL", "MSFT"):
            artifact_dir = tmp_path / ".atlas" / "research" / sym
            artifact_dir.mkdir(parents=True)
            artifact = {
                "run_id": f"run_{sym}",
                "symbol": sym,
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
                "artifact_path": f".atlas/research/{sym}/run_{sym}.json",
                "metadata": {},
                "created_at": "2026-01-01T00:00:00+00:00",
                "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
            }
            (artifact_dir / f"run_{sym}.json").write_text(json.dumps(artifact), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "check-artifacts", "--symbol", "AAPL", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["counts"]["research"] == 1


class TestCheckArtifactsSymlink:
    def test_symlink_outside_workspace_detected(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        outside = tmp_path.parent / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        artifact_dir = tmp_path / ".atlas" / "research" / "AAPL"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "link.json").symlink_to(outside)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "check-artifacts", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        codes = {i["code"] for i in out["issues"]}
        assert "unsafe_path" in codes or "malformed_json" in codes


class TestCheckArtifactsReadOnly:
    def test_no_files_created(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        artifact_dir = tmp_path / ".atlas" / "research" / "AAPL"
        artifact_dir.mkdir(parents=True)
        artifact = {
            "run_id": "run1",
            "symbol": "AAPL",
            "mode": "paper",
            "provider": "deterministic",
            "summary": "s",
            "artifact_path": ".atlas/research/AAPL/run1.json",
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
            "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        }
        (artifact_dir / "run1.json").write_text(json.dumps(artifact), encoding="utf-8")
        before = set(tmp_path.rglob("*"))
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "check-artifacts"])
        after = set(tmp_path.rglob("*"))
        assert before == after

    def test_no_pending_orders_created(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "check-artifacts"])
        pending = tmp_path / "pending_orders"
        assert not pending.exists() or not any(pending.iterdir())


class TestCheckArtifactsNoExecutionPath:
    def test_no_broker_calls(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config), \
             patch("atlas_agent.execution.order_router.OrderRouter.route") as mock_route, \
             patch("atlas_agent.execution.approval.ApprovalManager.create_pending_order") as mock_approval, \
             patch("atlas_agent.brokers.resolver.BrokerResolver.resolve_execution_broker") as mock_broker:
            main(["research", "check-artifacts"])
            mock_route.assert_not_called()
            mock_approval.assert_not_called()
            mock_broker.assert_not_called()


class TestCheckArtifactsNoBrokerCredentials:
    def test_works_without_broker_env(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "check-artifacts"]) == 0
