from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from atlas_agent.agent.autonomous_paper import (
    AutonomousPaperResult,
    build_autonomous_paper_evidence,
    run_autonomous_paper_loop,
)
from atlas_agent.cli import main as cli_main
from atlas_agent.config import AtlasConfig


SAMPLE_CSV = Path(__file__).resolve().parents[1] / "data" / "sample" / "ohlcv.csv"


REQUIRED_DISCIPLINE_SENTENCE = (
    "User discipline cannot override Atlas risk gates, approval queues, kill switch, "
    "audit logging, broker sync checks, reference price requirements, or live-trading safeguards."
)


def _write_discipline(workspace: Path) -> Path:
    path = workspace / ".atlas" / "discipline.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Atlas User Discipline Profile\n\n"
        "## Decision temperament\nCautious and evidence-seeking.\n\n"
        "## Reasoning style\nStep-by-step and transparent.\n\n"
        "## Communication style\nConcise, structured, and respectful.\n\n"
        "## Risk posture\nConservative.\n\n"
        "## Uncertainty handling\nExplicitly state confidence levels.\n\n"
        "## No-trade bias\nDefault to no action unless the case is compelling.\n\n"
        "## Forbidden overrides\n"
        f"{REQUIRED_DISCIPLINE_SENTENCE}\n",
        encoding="utf-8",
    )
    return path


def _make_config(tmp_path: Path, **overrides: object) -> AtlasConfig:
    data_dir = tmp_path / "data" / "sample"
    data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(SAMPLE_CSV, data_dir / "ohlcv.csv")

    cfg_dict: dict[str, object] = {
        "trading_mode": "paper",
        "workspace_root": tmp_path,
        "memory_dir": tmp_path / "memory",
        "reports_dir": tmp_path / "reports",
        "events_dir": tmp_path / "events",
        "pending_orders_dir": tmp_path / "pending_orders",
        "audit": {"audit_dir": tmp_path / "audit"},
        "market": {"symbol": "DEMO-SYMBOL"},
        "backtest": {
            "initial_cash": 10000.0,
            "data_path": data_dir / "ohlcv.csv",
        },
        "risk": {
            "max_position_notional": 20000.0,
            "max_order_notional": 20000.0,
            "minimum_confidence": 0.0,
        },
        "safety": {"kill_switch_enabled": False},
    }
    cfg_dict.update(overrides)
    return AtlasConfig.model_validate(cfg_dict)


def _read_decisions(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class TestAutonomousPaperLoopHappyPath:
    def test_executes_paper_trade(self, tmp_path: Path):
        config = _make_config(tmp_path)
        result = run_autonomous_paper_loop(
            config=config,
            max_cycles=5,
            strategy_id="buy_and_hold",
            strategy_parameters={"position_pct": 0.2},
        )
        assert result.status == "completed"
        assert result.mode == "paper"
        assert result.trades_executed >= 1
        assert result.decisions == 5
        assert Path(result.decisions_path).exists()
        assert Path(result.manifest_path).exists()
        decisions = _read_decisions(Path(result.decisions_path))
        assert len(decisions) == 5
        assert any(d["decision_state"] == "paper_executed" for d in decisions)

    def test_audit_artifacts_created(self, tmp_path: Path):
        config = _make_config(tmp_path)
        result = run_autonomous_paper_loop(
            config=config,
            max_cycles=3,
            strategy_id="buy_and_hold",
            strategy_parameters={"position_pct": 0.2},
        )
        audit_path = Path(result.audit_log_path)
        assert audit_path.exists()
        manifest_path = Path(result.manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["run_id"] == result.run_id
        assert manifest["mode"] == "paper"


class TestAutonomousPaperLoopNoTradePath:
    def test_moving_average_cross_no_signal(self, tmp_path: Path):
        config = _make_config(tmp_path)
        result = run_autonomous_paper_loop(
            config=config,
            max_cycles=3,
            strategy_id="moving_average_cross",
        )
        assert result.status == "completed"
        assert result.no_trade_count == 3
        assert result.trades_executed == 0
        assert result.trades_blocked == 0


class TestAutonomousPaperLoopRiskBlockedPath:
    def test_symbol_not_allowlisted_blocked(self, tmp_path: Path):
        config = _make_config(
            tmp_path,
            risk={
                "max_position_notional": 20000.0,
                "max_order_notional": 20000.0,
                "minimum_confidence": 0.0,
                "symbol_allowlist": ["OTHER"],
            },
        )
        result = run_autonomous_paper_loop(
            config=config,
            max_cycles=3,
            strategy_id="buy_and_hold",
            strategy_parameters={"position_pct": 0.2},
        )
        assert result.status == "completed"
        assert result.trades_blocked >= 1
        assert result.trades_executed == 0
        decisions = _read_decisions(Path(result.decisions_path))
        blocked = [d for d in decisions if d["decision_state"] == "risk_blocked"]
        assert blocked
        assert any("allowed_symbols" in str(b["risk_result"]) for b in blocked)


class TestAutonomousPaperLoopMalformedConfig:
    def test_missing_symbol_fails_closed(self, tmp_path: Path):
        config = _make_config(tmp_path, market={"symbol": ""}, backtest={"default_symbol": ""})
        result = run_autonomous_paper_loop(config=config, max_cycles=3)
        assert result.status == "failed"
        assert result.decisions == 0
        assert any("symbol" in err.lower() for err in result.errors)

    def test_missing_data_path_fails_closed(self, tmp_path: Path):
        config = _make_config(tmp_path, backtest={"data_path": tmp_path / "missing.csv"})
        result = run_autonomous_paper_loop(config=config, max_cycles=3)
        assert result.status == "failed"
        assert result.decisions == 0


class TestAutonomousPaperLoopSafetyBoundaries:
    def test_broker_submit_path_unreachable(self, tmp_path: Path):
        config = _make_config(tmp_path)
        resolver_spy = mock.MagicMock(side_effect=AssertionError("live broker resolver must not be called"))
        with mock.patch(
            "atlas_agent.brokers.resolver.BrokerResolver.resolve_execution_broker",
            resolver_spy,
        ):
            result = run_autonomous_paper_loop(
                config=config,
                max_cycles=3,
                strategy_id="buy_and_hold",
                strategy_parameters={"position_pct": 0.2},
            )
        assert result.status == "completed"
        resolver_spy.assert_not_called()

    def test_provider_execution_not_triggered(self, tmp_path: Path):
        config = _make_config(tmp_path)
        provider_spy = mock.MagicMock(side_effect=AssertionError("provider must not be called"))
        with mock.patch(
            "atlas_agent.providers.factory.get_provider_from_runtime_config",
            provider_spy,
        ):
            result = run_autonomous_paper_loop(
                config=config,
                max_cycles=3,
                strategy_id="buy_and_hold",
                strategy_parameters={"position_pct": 0.2},
            )
        assert result.status == "completed"
        provider_spy.assert_not_called()

    def test_deterministic_replay(self, tmp_path: Path):
        config = _make_config(tmp_path)
        run_id = "replay-run-001"
        result1 = run_autonomous_paper_loop(
            config=config,
            run_id=run_id,
            max_cycles=5,
            strategy_id="buy_and_hold",
            strategy_parameters={"position_pct": 0.2},
        )
        result2 = run_autonomous_paper_loop(
            config=config,
            run_id=run_id + "-2",
            max_cycles=5,
            strategy_id="buy_and_hold",
            strategy_parameters={"position_pct": 0.2},
        )
        assert result1.trades_executed == result2.trades_executed
        assert result1.trades_blocked == result2.trades_blocked
        assert result1.no_trade_count == result2.no_trade_count
        decisions1 = _read_decisions(Path(result1.decisions_path))
        decisions2 = _read_decisions(Path(result2.decisions_path))
        for d1, d2 in zip(decisions1, decisions2):
            assert d1["decision_state"] == d2["decision_state"]
            assert d1["proposed_action"] == d2["proposed_action"]


class TestAutonomousPaperEvidenceBundle:
    def test_build_evidence_bundle(self, tmp_path: Path):
        config = _make_config(tmp_path)
        result = run_autonomous_paper_loop(
            config=config,
            max_cycles=3,
            strategy_id="buy_and_hold",
            strategy_parameters={"position_pct": 0.2},
        )
        bundle_dir = build_autonomous_paper_evidence(
            run_id=result.run_id,
            decisions_path=result.decisions_path,
            manifest_path=result.manifest_path,
            output_dir=tmp_path / "evidence",
        )
        assert bundle_dir.exists()
        assert (bundle_dir / "decisions.jsonl").exists()
        assert (bundle_dir / "manifest.json").exists()
        evidence = json.loads((bundle_dir / "evidence.json").read_text(encoding="utf-8"))
        assert evidence["mode"] == "paper"
        assert evidence["run_id"] == result.run_id


class TestAutonomousPaperCli:
    def test_cli_runs_autonomous_paper(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        data_dir = tmp_path / "data" / "sample"
        data_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(SAMPLE_CSV, data_dir / "ohlcv.csv")
        _write_discipline(tmp_path)
        for dirname in ("memory", "events", "audit", "reports", "pending_orders"):
            (tmp_path / dirname).mkdir(parents=True, exist_ok=True)
        config_path = tmp_path / ".atlas" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            '[market]\nsymbol = "DEMO-SYMBOL"\n\n'
            '[backtest]\ninitial_cash = 10000.0\ndata_path = "data/sample/ohlcv.csv"\n\n'
            '[risk]\nmax_position_notional = 20000.0\nmax_order_notional = 20000.0\nminimum_confidence = 0.0\n\n'
            '[audit]\naudit_dir = "audit"\n',
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", [
            "atlas", "agent", "autonomous-paper", "--max-cycles", "2", "--json",
        ])
        code = cli_main()
        assert code == 0
        assert (tmp_path / "reports" / "autonomous_paper").exists()

    def test_cli_rejects_live_mode_argument(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _write_discipline(tmp_path)
        for dirname in ("memory", "events", "audit", "reports", "pending_orders"):
            (tmp_path / dirname).mkdir(parents=True, exist_ok=True)
        config_path = tmp_path / ".atlas" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            '[market]\nsymbol = "DEMO-SYMBOL"\n\n'
            '[backtest]\ninitial_cash = 10000.0\ndata_path = "data/sample/ohlcv.csv"\n\n'
            '[risk]\nmax_position_notional = 20000.0\nmax_order_notional = 20000.0\nminimum_confidence = 0.0\n\n'
            '[audit]\naudit_dir = "audit"\n',
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", [
            "atlas", "agent", "autonomous-paper", "--mode", "live",
        ])
        with pytest.raises(SystemExit):
            cli_main()
