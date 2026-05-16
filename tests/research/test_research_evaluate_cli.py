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


def _make_csv(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    import csv

    path = tmp_path / "data" / "ohlcv.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("date,open,high,low,close,volume\n", encoding="utf-8")
        return path
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _default_csv(tmp_path: Path) -> Path:
    return _make_csv(
        tmp_path,
        [
            {"date": "2026-01-01", "open": "100", "high": "105", "low": "99", "close": "102", "volume": "1000"},
            {"date": "2026-01-02", "open": "102", "high": "106", "low": "101", "close": "104", "volume": "1200"},
        ],
    )


class TestResearchEvaluateCreatesArtifact:
    def test_evaluate_creates_artifact(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        csv_path = _default_csv(tmp_path)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "evaluate", plan_id, "--data", str(csv_path)]) == 0
        out = capsys.readouterr().out
        assert "Paper plan evaluation created" in out
        assert "Symbol: AAPL" in out
        assert f"Source Plan ID: {plan_id}" in out
        assert "Evaluation ID:" in out
        assert "Artifact:" in out
        assert ".atlas/research/AAPL/evaluations/" in out

    def test_evaluate_artifact_json_valid(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        csv_path = _default_csv(tmp_path)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "evaluate", plan_id, "--data", str(csv_path), "--json"])
        out = json.loads(capsys.readouterr().out.strip())
        e_path = tmp_path / out["artifact_path"]
        assert e_path.exists()
        data = json.loads(e_path.read_text())
        assert data["mode"] == "paper"
        assert data["source_plan_id"] == plan_id
        assert data["symbol"] == "AAPL"
        assert "evaluation_id" in data
        assert "checks" in data
        assert data["recommendation"] == "paper_evaluation_ready"


class TestResearchEvaluateJsonOutput:
    def test_json_output_shape(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        csv_path = _default_csv(tmp_path)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "evaluate", plan_id, "--data", str(csv_path), "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        assert data["status"] == "research_evaluation_created"
        assert data["symbol"] == "AAPL"
        assert data["source_plan_id"] == plan_id
        assert "evaluation_id" in data
        assert "recommendation" in data
        assert "artifact_path" in data
        assert "metrics" in data
        assert not data["artifact_path"].startswith("/")
        assert "/Users/" not in data["artifact_path"]
        assert "/private/var/" not in data["artifact_path"]

    def test_json_no_secrets(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        csv_path = _default_csv(tmp_path)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "evaluate", plan_id, "--data", str(csv_path), "--json"])
        out = capsys.readouterr().out.strip()
        assert "sk-" not in out.lower()
        assert "pplx-" not in out.lower()


class TestResearchEvaluateTextOutput:
    def test_text_output_shape(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        csv_path = _default_csv(tmp_path)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "evaluate", plan_id, "--data", str(csv_path)]) == 0
        out = capsys.readouterr().out
        assert "Paper plan evaluation created" in out
        assert "Symbol:" in out
        assert "Source Plan ID:" in out
        assert "Evaluation ID:" in out
        assert "Recommendation:" in out
        assert "Rows:" in out
        assert "Artifact:" in out

    def test_text_no_absolute_paths(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        csv_path = _default_csv(tmp_path)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "evaluate", plan_id, "--data", str(csv_path)])
        out = capsys.readouterr().out
        assert "/Users/" not in out
        assert "/private/var/" not in out


class TestResearchEvaluateNotFound:
    def test_not_found_text(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        csv_path = _default_csv(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "evaluate", "missing-id", "--data", str(csv_path)])
        assert code == 1
        out = capsys.readouterr().out
        assert "not found" in out.lower() or "research evaluate skipped safely" in out.lower()

    def test_not_found_json(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        csv_path = _default_csv(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "evaluate", "missing-id", "--data", str(csv_path), "--json"])
        assert code == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False
        assert "status" in data


class TestResearchEvaluateInvalidPlanId:
    def test_invalid_plan_id_text(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        csv_path = _default_csv(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "evaluate", "../secret", "--data", str(csv_path)])
        assert code == 1
        out = capsys.readouterr().out
        assert "unsafe" in out.lower() or "research evaluate skipped safely" in out.lower()

    def test_invalid_plan_id_json(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        csv_path = _default_csv(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "evaluate", "../secret", "--data", str(csv_path), "--json"])
        assert code == 1
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is False


class TestResearchEvaluateAmbiguous:
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
        csv_path = _default_csv(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "evaluate", "sharedplanid", "--data", str(csv_path)])
        assert code == 1
        out = capsys.readouterr().out
        assert "ambiguous" in out.lower()


class TestResearchEvaluateMalformedSource:
    def test_malformed_source_plan(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        plans_dir = tmp_path / ".atlas" / "research" / "AAPL" / "plans"
        plans_dir.mkdir(parents=True)
        (plans_dir / "validplanid.json").write_text("not json", encoding="utf-8")
        csv_path = _default_csv(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "evaluate", "validplanid", "--data", str(csv_path)])
        assert code == 1
        out = capsys.readouterr().out
        assert "malformed" in out.lower() or "research evaluate skipped safely" in out.lower()


class TestResearchEvaluateMissingData:
    def test_missing_data_file(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        missing_csv = tmp_path / "missing.csv"
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "evaluate", plan_id, "--data", str(missing_csv)])
        assert code == 1
        out = capsys.readouterr().out
        assert "data" in out.lower() or "research evaluate skipped safely" in out.lower()


class TestResearchEvaluateMalformedData:
    def test_malformed_data_file(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        bad_csv = tmp_path / "bad.csv"
        bad_csv.write_text("not,a,csv\n1,2\n3", encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "evaluate", plan_id, "--data", str(bad_csv)])
        assert code == 1
        out = capsys.readouterr().out
        assert "data" in out.lower() or "research evaluate skipped safely" in out.lower()


class TestResearchEvaluateMissingCloseColumn:
    def test_missing_close_column(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        csv_path = _make_csv(tmp_path, [{"date": "2026-01-01", "open": "100"}])
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "evaluate", plan_id, "--data", str(csv_path)])
        assert code == 1
        out = capsys.readouterr().out
        assert "data" in out.lower() or "research evaluate skipped safely" in out.lower()


class TestResearchEvaluateFailedChecks:
    def test_missing_verification_steps(self, tmp_path: Path, capsys, monkeypatch) -> None:
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
            "risk_notes": ["r"],
            "invalidation_checks": ["i"],
            "paper_only_actions": ["a"],
            "verification_steps": [],
            "warnings": [],
            "artifact_path": "",
            "metadata": {},
        }
        (plans_dir / "plan1.json").write_text(json.dumps(plan_data), encoding="utf-8")
        csv_path = _default_csv(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "evaluate", "plan1", "--data", str(csv_path), "--json"]) == 0
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
            "thesis_recap": "guaranteed profit for everyone",
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
        csv_path = _default_csv(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "evaluate", "plan2", "--data", str(csv_path), "--json"]) == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["ok"] is True
        assert data["recommendation"] == "manual_review_required"
        assert data["failed_checks"] > 0
        assert "guaranteed profit" not in out.lower()


class TestResearchEvaluateEventSafety:
    def test_event_payload_safe(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        csv_path = _default_csv(tmp_path)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "evaluate", plan_id, "--data", str(csv_path)])
        events_dir = tmp_path / "events"
        event_files = list(events_dir.glob("*.jsonl"))
        assert len(event_files) >= 1
        latest = event_files[-1]
        lines = latest.read_text().strip().splitlines()
        eval_event = None
        for line in lines:
            ev = json.loads(line)
            if ev.get("event_type") == "research_evaluation_created":
                eval_event = ev
                break
        assert eval_event is not None
        payload = eval_event["payload"]
        assert "evaluation_id" in payload
        assert "source_plan_id" in payload
        assert "source_run_id" in payload
        assert "symbol" in payload
        assert "recommendation" in payload
        assert "artifact_path" in payload
        assert "row_count" in payload
        # Must NOT contain full bodies
        assert "checks" not in payload
        assert "thesis_recap" not in payload
        assert "risk_notes" not in payload


class TestResearchEvaluateNoExecutionPath:
    def test_no_broker_calls(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        csv_path = _default_csv(tmp_path)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config), \
             patch("atlas_agent.execution.order_router.OrderRouter.route") as mock_route, \
             patch("atlas_agent.execution.approval.ApprovalManager.create_pending_order") as mock_approval, \
             patch("atlas_agent.brokers.resolver.BrokerResolver.resolve_execution_broker") as mock_broker:
            main(["research", "evaluate", plan_id, "--data", str(csv_path)])
            mock_route.assert_not_called()
            mock_approval.assert_not_called()
            mock_broker.assert_not_called()


class TestResearchEvaluateNoPendingOrder:
    def test_no_pending_orders_created(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        csv_path = _default_csv(tmp_path)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "evaluate", plan_id, "--data", str(csv_path)])
        pending = tmp_path / "pending_orders"
        assert not pending.exists() or not any(pending.iterdir())


class TestResearchEvaluateNoBrokerCredentials:
    def test_works_without_broker_env(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        csv_path = _default_csv(tmp_path)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "evaluate", plan_id, "--data", str(csv_path)]) == 0


class TestResearchEvaluateStableSchema:
    def test_required_keys_exist(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        csv_path = _default_csv(tmp_path)
        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "evaluate", plan_id, "--data", str(csv_path), "--json"])
        out = json.loads(capsys.readouterr().out.strip())
        e_path = tmp_path / out["artifact_path"]
        data = json.loads(e_path.read_text())
        required_keys = [
            "evaluation_id", "source_plan_id", "source_run_id",
            "symbol", "mode", "provider", "source_plan_path",
            "data_source", "data_summary", "checks", "metrics",
            "recommendation", "artifact_path", "metadata",
        ]
        for k in required_keys:
            assert k in data, f"Missing key: {k}"
        check_names = {c["name"] for c in data["checks"]}
        required_checks = [
            "plan_loaded", "paper_only_mode", "data_file_loaded",
            "data_has_required_columns", "data_has_rows",
            "data_symbol_context", "plan_has_verification_steps",
            "plan_has_invalidation_checks", "no_live_authorization_language",
        ]
        for name in required_checks:
            assert name in check_names, f"Missing check: {name}"
        assert data["recommendation"] in ("paper_evaluation_ready", "manual_review_required")

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
        csv_path = _default_csv(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "evaluate", "good", "--data", str(csv_path), "--json"])
        out = json.loads(capsys.readouterr().out.strip())
        assert out["recommendation"] == "paper_evaluation_ready"

        # Bad plan (missing data means some checks fail, but let's make a plan with missing checks)
        bad = {
            "plan_id": "bad", "source_run_id": "r", "symbol": "AAPL",
            "created_at": "2026-01-01T00:00:00+00:00", "mode": "paper",
            "provider": "deterministic", "source_artifact_path": ".atlas/research/AAPL/r.json",
            "thesis_recap": "t", "constraints": [],
            "risk_notes": [], "invalidation_checks": [],
            "paper_only_actions": [], "verification_steps": [],
            "warnings": [], "artifact_path": "", "metadata": {},
        }
        (plans_dir / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "evaluate", "bad", "--data", str(csv_path), "--json"])
        out = json.loads(capsys.readouterr().out.strip())
        assert out["recommendation"] == "manual_review_required"
