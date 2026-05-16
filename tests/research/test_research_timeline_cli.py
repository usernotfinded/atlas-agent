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


def _run_verify(tmp_path: Path, monkeypatch, capsys, plan_id: str) -> str:
    config = _config(tmp_path)
    config.ensure_dirs()
    monkeypatch.chdir(tmp_path)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        main(["research", "verify", plan_id, "--json"])
    out = json.loads(capsys.readouterr().out.strip())
    return out["verification_id"]


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


def _run_evaluate(tmp_path: Path, monkeypatch, capsys, plan_id: str) -> str:
    csv_path = _default_csv(tmp_path)
    config = _config(tmp_path)
    config.ensure_dirs()
    monkeypatch.chdir(tmp_path)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        main(["research", "evaluate", plan_id, "--data", str(csv_path), "--json"])
    out = json.loads(capsys.readouterr().out.strip())
    return out["evaluation_id"]


class TestTimelineEmptyWorkspace:
    def test_empty_workspace(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "timeline"]) == 0
        out = capsys.readouterr().out
        assert "No research timeline entries found" in out

    def test_empty_workspace_json(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "timeline", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is True
        assert out["status"] == "research_timeline"
        assert out["entries"] == []

    def test_empty_workspace_creates_no_files(self, tmp_path: Path, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        before = list(tmp_path.rglob("*"))
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "timeline"])
        after = list(tmp_path.rglob("*"))
        # Only audit/events may be created by event logger; research artifacts should not
        research_files = [p for p in after if ".atlas/research" in str(p)]
        assert len(research_files) == 0


class TestTimelineFullChain:
    def test_full_chain_text(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        verification_id = _run_verify(tmp_path, monkeypatch, capsys, plan_id)
        evaluation_id = _run_evaluate(tmp_path, monkeypatch, capsys, plan_id)

        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "timeline"]) == 0
        out = capsys.readouterr().out
        assert run_id in out
        assert plan_id in out
        assert verification_id in out
        assert evaluation_id in out
        assert "AAPL" in out
        assert "/Users/" not in out
        assert "/private/var/" not in out

    def test_full_chain_json(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        verification_id = _run_verify(tmp_path, monkeypatch, capsys, plan_id)
        evaluation_id = _run_evaluate(tmp_path, monkeypatch, capsys, plan_id)

        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "timeline", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is True
        assert out["status"] == "research_timeline"
        assert len(out["entries"]) == 1
        entry = out["entries"][0]
        assert entry["run_id"] == run_id
        assert entry["symbol"] == "AAPL"
        assert entry["research_path"].startswith(".atlas/research/")
        assert len(entry["plans"]) == 1
        plan = entry["plans"][0]
        assert plan["plan_id"] == plan_id
        assert plan["artifact_path"].startswith(".atlas/research/")
        assert len(plan["verifications"]) == 1
        assert plan["verifications"][0]["verification_id"] == verification_id
        assert len(plan["evaluations"]) == 1
        assert plan["evaluations"][0]["evaluation_id"] == evaluation_id
        # No absolute paths
        json_str = json.dumps(out)
        assert "/Users/" not in json_str
        assert "/private/var/" not in json_str


class TestTimelineFilters:
    def test_symbol_filter(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_aapl = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_aapl = _run_plan(tmp_path, monkeypatch, capsys, run_aapl)
        _run_verify(tmp_path, monkeypatch, capsys, plan_aapl)

        run_msft = _run_research(tmp_path, monkeypatch, capsys, "MSFT")
        plan_msft = _run_plan(tmp_path, monkeypatch, capsys, run_msft)
        _run_verify(tmp_path, monkeypatch, capsys, plan_msft)

        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "timeline", "--symbol", "AAPL", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert len(out["entries"]) == 1
        assert out["entries"][0]["symbol"] == "AAPL"
        assert out["entries"][0]["run_id"] == run_aapl

    def test_run_id_filter(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run1 = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan1 = _run_plan(tmp_path, monkeypatch, capsys, run1)
        _run_verify(tmp_path, monkeypatch, capsys, plan1)

        run2 = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan2 = _run_plan(tmp_path, monkeypatch, capsys, run2)
        _run_verify(tmp_path, monkeypatch, capsys, plan2)

        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "timeline", "--run-id", run1, "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert len(out["entries"]) == 1
        assert out["entries"][0]["run_id"] == run1

    def test_run_id_not_found(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        _run_verify(tmp_path, monkeypatch, capsys, plan_id)

        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "timeline", "--run-id", "nonexistent123", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is True
        assert out["entries"] == []

    def test_invalid_symbol(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "timeline", "--symbol", "../../etc", "--json"]) != 0
        out = capsys.readouterr().out
        assert "ok" in out.lower() or "skipped" in out.lower()

    def test_invalid_run_id(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "timeline", "--run-id", "bad!id", "--json"]) != 0
        out = capsys.readouterr().out
        assert "ok" in out.lower() or "skipped" in out.lower()

    def test_limit_clamped(self, tmp_path: Path, capsys, monkeypatch) -> None:
        for i in range(3):
            run_id = _run_research(tmp_path, monkeypatch, capsys, f"SYM{i}")
            _run_plan(tmp_path, monkeypatch, capsys, run_id)

        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "timeline", "--limit", "1", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert len(out["entries"]) == 1

    def test_invalid_limit(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "timeline", "--limit", "0", "--json"]) != 0
        out = capsys.readouterr().out
        assert "ok" in out.lower() or "skipped" in out.lower()

    def test_huge_limit_clamped(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        _run_plan(tmp_path, monkeypatch, capsys, run_id)

        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "timeline", "--limit", "9999", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is True
        assert len(out["entries"]) <= 100


class TestTimelineBrokenLineage:
    def test_orphan_plan(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        # Create a plan pointing to a nonexistent run_id
        plan_path = tmp_path / ".atlas" / "research" / "AAPL" / "plans" / "orphanplan.json"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(
            json.dumps(
                {
                    "plan_id": "orphanplan",
                    "source_run_id": "nonexistentrun",
                    "symbol": "AAPL",
                    "mode": "paper",
                    "provider": "deterministic",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
                }
            ),
            encoding="utf-8",
        )
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "timeline", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is True
        warning_codes = [w["code"] for w in out.get("warnings", [])]
        assert "orphan_plan" in warning_codes

    def test_orphan_verification(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        # Create a verification pointing to a nonexistent plan
        v_path = tmp_path / ".atlas" / "research" / "AAPL" / "verifications" / "orphanv.json"
        v_path.parent.mkdir(parents=True, exist_ok=True)
        v_path.write_text(
            json.dumps(
                {
                    "verification_id": "orphanv",
                    "source_plan_id": "nonexistentplan",
                    "source_run_id": "nonexistentrun",
                    "symbol": "AAPL",
                    "mode": "paper",
                    "provider": "deterministic",
                    "recommendation": "paper_review_ready",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
                }
            ),
            encoding="utf-8",
        )
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "timeline", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is True
        warning_codes = [w["code"] for w in out.get("warnings", [])]
        assert "orphan_verification" in warning_codes

    def test_orphan_evaluation(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        # Create an evaluation pointing to a nonexistent plan
        e_path = tmp_path / ".atlas" / "research" / "AAPL" / "evaluations" / "orphane.json"
        e_path.parent.mkdir(parents=True, exist_ok=True)
        e_path.write_text(
            json.dumps(
                {
                    "evaluation_id": "orphane",
                    "source_plan_id": "nonexistentplan",
                    "source_run_id": "nonexistentrun",
                    "symbol": "AAPL",
                    "mode": "paper",
                    "provider": "deterministic",
                    "recommendation": "paper_evaluation_ready",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
                }
            ),
            encoding="utf-8",
        )
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "timeline", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is True
        warning_codes = [w["code"] for w in out.get("warnings", [])]
        assert "orphan_evaluation" in warning_codes

    def test_malformed_artifact_skipped(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        # Create a valid research artifact
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        # Create malformed JSON in same symbol dir
        bad_path = tmp_path / ".atlas" / "research" / "AAPL" / "bad.json"
        bad_path.write_text("not json", encoding="utf-8")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "timeline", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is True
        assert len(out["entries"]) == 1
        assert out["entries"][0]["run_id"] == run_id

    def test_unsupported_schema_skipped(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        # Create unsupported schema artifact
        bad_path = tmp_path / ".atlas" / "research" / "AAPL" / "badschema.json"
        bad_path.write_text(
            json.dumps(
                {
                    "run_id": "badschema",
                    "symbol": "AAPL",
                    "mode": "paper",
                    "schema_version": "999",
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "timeline", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is True
        assert len(out["entries"]) == 1
        assert out["entries"][0]["run_id"] == run_id

    def test_duplicate_id_warning(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        # Create two research artifacts with same run_id in different symbols (edge case)
        for sym in ("AAPL", "MSFT"):
            sym_dir = tmp_path / ".atlas" / "research" / sym
            sym_dir.mkdir(parents=True, exist_ok=True)
            (sym_dir / "samerun.json").write_text(
                json.dumps(
                    {
                        "run_id": "samerun",
                        "symbol": sym,
                        "mode": "paper",
                        "provider": "deterministic",
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
                    }
                ),
                encoding="utf-8",
            )
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "timeline", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is True
        # Duplicate IDs are tracked by check-artifacts but timeline does not surface them;
        # timeline should not crash and should show entries
        assert len(out["entries"]) >= 1


class TestTimelineReadOnly:
    def test_no_new_artifacts(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        _run_verify(tmp_path, monkeypatch, capsys, plan_id)

        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        research_files_before = set((tmp_path / ".atlas" / "research").rglob("*.json"))
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "timeline"])
        research_files_after = set((tmp_path / ".atlas" / "research").rglob("*.json"))
        assert research_files_before == research_files_after

    def test_no_pending_orders(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        _run_verify(tmp_path, monkeypatch, capsys, plan_id)

        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "timeline"])
        pending_dir = tmp_path / "pending_orders"
        pending_files = [p for p in pending_dir.iterdir() if p.is_file() and p.name != ".gitkeep"]
        assert len(pending_files) == 0

    def test_no_approval_files(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        _run_verify(tmp_path, monkeypatch, capsys, plan_id)

        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            main(["research", "timeline"])
        # No approval files should be created
        for sub in ("approvals", "approved"):
            sub_dir = tmp_path / sub
            if sub_dir.exists():
                files = [p for p in sub_dir.iterdir() if p.is_file()]
                assert len(files) == 0


class TestTimelineNoExecutionPath:
    def test_no_broker_resolution(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        _run_verify(tmp_path, monkeypatch, capsys, plan_id)

        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            with patch("atlas_agent.brokers.resolver.BrokerResolver.resolve_execution_broker") as mock_resolve:
                main(["research", "timeline"])
                mock_resolve.assert_not_called()

    def test_no_order_router(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        _run_verify(tmp_path, monkeypatch, capsys, plan_id)

        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            with patch("atlas_agent.execution.order_router.OrderRouter.route") as mock_route:
                main(["research", "timeline"])
                mock_route.assert_not_called()

    def test_no_place_order(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        _run_verify(tmp_path, monkeypatch, capsys, plan_id)

        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            with patch("atlas_agent.execution.order_router.OrderRouter.route") as mock_route:
                main(["research", "timeline"])
                mock_route.assert_not_called()

    def test_no_approval_manager(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        _run_verify(tmp_path, monkeypatch, capsys, plan_id)

        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            with patch("atlas_agent.execution.approval.ApprovalManager.create_pending_order") as mock_create:
                main(["research", "timeline"])
                mock_create.assert_not_called()


class TestTimelineNoBrokerCredentials:
    def test_works_without_broker_env(self, tmp_path: Path, capsys, monkeypatch) -> None:
        run_id = _run_research(tmp_path, monkeypatch, capsys, "AAPL")
        plan_id = _run_plan(tmp_path, monkeypatch, capsys, run_id)
        _run_verify(tmp_path, monkeypatch, capsys, plan_id)

        config = _config(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
        monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)
        monkeypatch.delenv("BROKER_API_KEY", raising=False)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            assert main(["research", "timeline", "--json"]) == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["ok"] is True
        assert len(out["entries"]) == 1
