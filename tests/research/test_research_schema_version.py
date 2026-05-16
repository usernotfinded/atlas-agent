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


class TestNewArtifactsHaveSchemaVersion:
    def test_research_artifact_includes_schema_version(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        artifact_file = tmp_path / ".atlas" / "research" / "AAPL" / f"{run_id}.json"
        data = json.loads(artifact_file.read_text())
        assert data["schema_version"] == RESEARCH_ARTIFACT_SCHEMA_VERSION

    def test_plan_artifact_includes_schema_version(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        plan_file = tmp_path / ".atlas" / "research" / "AAPL" / "plans" / f"{plan_id}.json"
        data = json.loads(plan_file.read_text())
        assert data["schema_version"] == RESEARCH_ARTIFACT_SCHEMA_VERSION

    def test_verification_artifact_includes_schema_version(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "verify", plan_id, "--json"])
        out = json.loads(capsys.readouterr().out.strip())
        v_file = tmp_path / out["artifact_path"]
        data = json.loads(v_file.read_text())
        assert data["schema_version"] == RESEARCH_ARTIFACT_SCHEMA_VERSION

    def test_evaluation_artifact_includes_schema_version(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        csv_path = _default_csv(tmp_path)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "evaluate", plan_id, "--data", str(csv_path), "--json"])
        out = json.loads(capsys.readouterr().out.strip())
        e_file = tmp_path / out["artifact_path"]
        data = json.loads(e_file.read_text())
        assert data["schema_version"] == RESEARCH_ARTIFACT_SCHEMA_VERSION


class TestLegacyArtifactCompatibility:
    def test_legacy_research_artifact_without_schema_version_loads(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        artifact_dir = tmp_path / ".atlas" / "research" / "AAPL"
        artifact_dir.mkdir(parents=True)
        run_id = "legacyrunid12345"
        artifact = {
            "run_id": run_id,
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
            "artifact_path": f".atlas/research/AAPL/{run_id}.json",
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        (artifact_dir / f"{run_id}.json").write_text(json.dumps(artifact), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "show", run_id, "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is True
        assert out["artifact"]["run_id"] == run_id

    def test_legacy_research_artifact_can_plan(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        artifact_dir = tmp_path / ".atlas" / "research" / "AAPL"
        artifact_dir.mkdir(parents=True)
        run_id = "legacyrunid12345"
        artifact = {
            "run_id": run_id,
            "symbol": "AAPL",
            "mode": "paper",
            "provider": "deterministic",
            "summary": "s",
            "thesis": "t",
            "market_context": "m",
            "risks": ["r"],
            "invalidation_conditions": ["i"],
            "paper_only_plan": "p",
            "memory_hits": [],
            "citations": [],
            "warnings": [],
            "artifact_path": f".atlas/research/AAPL/{run_id}.json",
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        (artifact_dir / f"{run_id}.json").write_text(json.dumps(artifact), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "plan", run_id, "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is True
        assert "plan_id" in out

    def test_legacy_plan_artifact_without_schema_version_loads(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        plans_dir = tmp_path / ".atlas" / "research" / "AAPL" / "plans"
        plans_dir.mkdir(parents=True)
        plan_id = "legacyplanid12345"
        plan = {
            "plan_id": plan_id,
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
            "artifact_path": f".atlas/research/AAPL/plans/{plan_id}.json",
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        (plans_dir / f"{plan_id}.json").write_text(json.dumps(plan), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "verify", plan_id, "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is True
        assert "verification_id" in out

    def test_legacy_plan_artifact_can_evaluate(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        plans_dir = tmp_path / ".atlas" / "research" / "AAPL" / "plans"
        plans_dir.mkdir(parents=True)
        csv_path = _default_csv(tmp_path)
        plan_id = "legacyplanid12345"
        plan = {
            "plan_id": plan_id,
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
            "artifact_path": f".atlas/research/AAPL/plans/{plan_id}.json",
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        (plans_dir / f"{plan_id}.json").write_text(json.dumps(plan), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "evaluate", plan_id, "--data", str(csv_path), "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is True
        assert "evaluation_id" in out


class TestUnsupportedSchemaFailsClosed:
    def test_unsupported_research_schema_show_fails(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        artifact_dir = tmp_path / ".atlas" / "research" / "AAPL"
        artifact_dir.mkdir(parents=True)
        run_id = "badschema12345"
        artifact = {
            "run_id": run_id,
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
            "artifact_path": f".atlas/research/AAPL/{run_id}.json",
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
            "schema_version": "999",
        }
        (artifact_dir / f"{run_id}.json").write_text(json.dumps(artifact), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "show", run_id, "--json"])
        assert code == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert "unsupported" in data.get("status", "").lower() or "schema" in data.get("message", "").lower()

    def test_unsupported_research_schema_plan_fails(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        artifact_dir = tmp_path / ".atlas" / "research" / "AAPL"
        artifact_dir.mkdir(parents=True)
        run_id = "badschema12345"
        artifact = {
            "run_id": run_id,
            "symbol": "AAPL",
            "mode": "paper",
            "provider": "deterministic",
            "summary": "s",
            "thesis": "t",
            "market_context": "m",
            "risks": ["r"],
            "invalidation_conditions": ["i"],
            "paper_only_plan": "p",
            "memory_hits": [],
            "citations": [],
            "warnings": [],
            "artifact_path": f".atlas/research/AAPL/{run_id}.json",
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
            "schema_version": "999",
        }
        (artifact_dir / f"{run_id}.json").write_text(json.dumps(artifact), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "plan", run_id, "--json"])
        assert code == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert "unsupported" in data.get("status", "").lower() or "schema" in data.get("message", "").lower()

    def test_unsupported_plan_schema_verify_fails(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        plans_dir = tmp_path / ".atlas" / "research" / "AAPL" / "plans"
        plans_dir.mkdir(parents=True)
        plan_id = "badplanid12345"
        plan = {
            "plan_id": plan_id,
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
            "artifact_path": f".atlas/research/AAPL/plans/{plan_id}.json",
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
            "schema_version": "999",
        }
        (plans_dir / f"{plan_id}.json").write_text(json.dumps(plan), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "verify", plan_id, "--json"])
        assert code == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert "unsupported" in data.get("status", "").lower() or "schema" in data.get("message", "").lower()

    def test_unsupported_plan_schema_evaluate_fails(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        plans_dir = tmp_path / ".atlas" / "research" / "AAPL" / "plans"
        plans_dir.mkdir(parents=True)
        csv_path = _default_csv(tmp_path)
        plan_id = "badplanid12345"
        plan = {
            "plan_id": plan_id,
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
            "artifact_path": f".atlas/research/AAPL/plans/{plan_id}.json",
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
            "schema_version": "999",
        }
        (plans_dir / f"{plan_id}.json").write_text(json.dumps(plan), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "evaluate", plan_id, "--data", str(csv_path), "--json"])
        assert code == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert "unsupported" in data.get("status", "").lower() or "schema" in data.get("message", "").lower()


class TestListSummaryHandlesUnsupportedSchema:
    def test_list_skips_unsupported_schema_safely(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        artifact_dir = tmp_path / ".atlas" / "research" / "AAPL"
        artifact_dir.mkdir(parents=True)
        # Good artifact
        good = {
            "run_id": "goodrunid",
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
            "artifact_path": ".atlas/research/AAPL/goodrunid.json",
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
            "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        }
        (artifact_dir / "goodrunid.json").write_text(json.dumps(good), encoding="utf-8")
        # Bad artifact
        bad = {
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
        (artifact_dir / "badrunid.json").write_text(json.dumps(bad), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "list", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is True
        run_ids = {i["run_id"] for i in out["items"]}
        assert "goodrunid" in run_ids
        assert "badrunid" not in run_ids

    def test_summary_skips_unsupported_schema_safely(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        artifact_dir = tmp_path / ".atlas" / "research" / "AAPL"
        artifact_dir.mkdir(parents=True)
        good = {
            "run_id": "goodrunid",
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
            "artifact_path": ".atlas/research/AAPL/goodrunid.json",
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
            "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        }
        (artifact_dir / "goodrunid.json").write_text(json.dumps(good), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "summary", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is True
        assert out["research_count"] >= 1


class TestEventPayloadSchemaVersion:
    def test_research_run_event_includes_schema_version(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        events_dir = tmp_path / "events"
        event_files = list(events_dir.glob("*.jsonl"))
        assert len(event_files) >= 1
        latest = event_files[-1]
        lines = latest.read_text().strip().splitlines()
        run_event = None
        for line in lines:
            ev = json.loads(line)
            if ev.get("event_type") == "research_run_created":
                run_event = ev
                break
        assert run_event is not None
        assert run_event["payload"]["schema_version"] == RESEARCH_ARTIFACT_SCHEMA_VERSION

    def test_event_payload_does_not_include_full_body(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        events_dir = tmp_path / "events"
        event_files = list(events_dir.glob("*.jsonl"))
        latest = event_files[-1]
        lines = latest.read_text().strip().splitlines()
        run_event = None
        for line in lines:
            ev = json.loads(line)
            if ev.get("event_type") == "research_run_created":
                run_event = ev
                break
        assert run_event is not None
        payload = run_event["payload"]
        assert "thesis" not in payload
        assert "risks" not in payload
        assert "summary" not in payload
