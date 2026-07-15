# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_autonomous_paper_scorecard.py
# PURPOSE: Verifies autonomous paper scorecard behavior and regression
#         expectations.
# DEPS:    json, shutil, sys, pathlib, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from atlas_agent.agent.autonomous_paper import (
    AutonomousPaperResult,
    run_autonomous_paper_loop,
)
from atlas_agent.agent.autonomous_paper_scorecard import (
    build_autonomous_paper_scorecard,
    render_autonomous_paper_scorecard_markdown,
    write_autonomous_paper_scorecard_reports,
)
from atlas_agent.cli import main as cli_main
from atlas_agent.config import AtlasConfig


# --- CONFIGURATION AND CONSTANTS ---

SAMPLE_CSV = Path(__file__).resolve().parents[1] / "data" / "sample" / "ohlcv.csv"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

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


def _scorecard_for_run(result: AutonomousPaperResult) -> dict[str, object]:
    return build_autonomous_paper_scorecard(result.decisions_path, result.manifest_path)


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


class TestAutonomousPaperScorecardHappyPath:
    def test_valid_completed_run_scorecard(self, tmp_path: Path):
        config = _make_config(tmp_path)
        result = run_autonomous_paper_loop(
            config=config,
            max_cycles=5,
            strategy_id="buy_and_hold",
            strategy_parameters={"position_pct": 0.2},
        )
        scorecard = _scorecard_for_run(result)
        assert scorecard["artifact_type"] == "autonomous_paper_scorecard"
        assert scorecard["schema_version"] == 1
        assert scorecard["mode"] == "paper"
        assert scorecard["run_id"] == result.run_id
        assert scorecard["promotion_state"] in (
            "paper_quality_observed",
            "eligible_for_shadow_live_review",
        )
        assert scorecard["scorecard_dimensions"]["schema_validity"]["passed"] is True
        assert scorecard["scorecard_dimensions"]["artifact_completeness"]["passed"] is True
        assert scorecard["decisions"] == 5

    def test_write_reports(self, tmp_path: Path):
        config = _make_config(tmp_path)
        result = run_autonomous_paper_loop(
            config=config,
            max_cycles=2,
            strategy_id="buy_and_hold",
            strategy_parameters={"position_pct": 0.2},
        )
        scorecard = _scorecard_for_run(result)
        output_dir = tmp_path / "scorecard"
        json_path, md_path = write_autonomous_paper_scorecard_reports(scorecard, output_dir)
        assert json_path.exists()
        assert md_path.exists()
        loaded = json.loads(json_path.read_text(encoding="utf-8"))
        assert loaded["promotion_state"] == scorecard["promotion_state"]
        md_text = md_path.read_text(encoding="utf-8")
        assert "Autonomous Paper Scorecard" in md_text
        assert "not financial advice" in md_text.lower()
        assert "not live-trading readiness" in md_text


class TestAutonomousPaperScorecardFailureModes:
    def test_missing_artifacts_not_evaluated(self, tmp_path: Path):
        scorecard = build_autonomous_paper_scorecard(
            str(tmp_path / "missing.jsonl"),
            str(tmp_path / "missing.json"),
        )
        assert scorecard["promotion_state"] == "not_evaluated"
        assert scorecard["blockers"]

    def test_malformed_jsonl_blocked(self, tmp_path: Path):
        decisions = tmp_path / "decisions.jsonl"
        manifest = tmp_path / "manifest.json"
        decisions.write_text("not json\n", encoding="utf-8")
        manifest.write_text(
            json.dumps({
                "run_id": "r",
                "mode": "paper",
                "symbol": "DEMO-SYMBOL",
                "strategy_id": "buy_and_hold",
                "data_source": "data/sample/ohlcv.csv",
                "bars_processed": 1,
                "decisions": 1,
                "trades_executed": 0,
                "trades_blocked": 0,
                "no_trade_count": 1,
                "decisions_path": str(decisions),
                "manifest_path": str(manifest),
            }),
            encoding="utf-8",
        )
        scorecard = build_autonomous_paper_scorecard(str(decisions), str(manifest))
        assert scorecard["promotion_state"] == "blocked"
        assert scorecard["scorecard_dimensions"]["schema_validity"]["passed"] is False

    def test_missing_manifest_blocked(self, tmp_path: Path):
        config = _make_config(tmp_path)
        result = run_autonomous_paper_loop(
            config=config,
            max_cycles=2,
            strategy_id="buy_and_hold",
            strategy_parameters={"position_pct": 0.2},
        )
        missing_manifest = tmp_path / "missing-manifest.json"
        scorecard = build_autonomous_paper_scorecard(
            result.decisions_path,
            str(missing_manifest),
        )
        assert scorecard["promotion_state"] == "blocked"
        assert scorecard["scorecard_dimensions"]["artifact_completeness"]["passed"] is False


class TestAutonomousPaperScorecardDimensionScoring:
    def test_risk_blocked_run_scoring(self, tmp_path: Path):
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
        scorecard = _scorecard_for_run(result)
        assert scorecard["scorecard_dimensions"]["risk_gate_compliance"]["passed"] is True
        assert scorecard["scorecard_dimensions"]["blocked_reason_quality"]["passed"] is True
        assert scorecard["trades_blocked"] >= 1

    def test_no_trade_run_scoring(self, tmp_path: Path):
        config = _make_config(tmp_path)
        result = run_autonomous_paper_loop(
            config=config,
            max_cycles=3,
            strategy_id="moving_average_cross",
        )
        scorecard = _scorecard_for_run(result)
        assert scorecard["scorecard_dimensions"]["no_trade_reason_quality"]["passed"] is True
        assert scorecard["no_trade_count"] == 3

    def test_kill_switch_blocked_run_scoring(self, tmp_path: Path):
        config = _make_config(tmp_path, safety={"kill_switch_enabled": True})
        result = run_autonomous_paper_loop(
            config=config,
            max_cycles=3,
            strategy_id="buy_and_hold",
            strategy_parameters={"position_pct": 0.2},
        )
        scorecard = _scorecard_for_run(result)
        assert scorecard["trades_executed"] == 0
        assert scorecard["scorecard_dimensions"]["kill_switch_compliance"]["passed"] is True

    def test_replay_mismatch_blocks_promotion(self, tmp_path: Path):
        config = _make_config(tmp_path)
        result = run_autonomous_paper_loop(
            config=config,
            max_cycles=3,
            strategy_id="buy_and_hold",
            strategy_parameters={"position_pct": 0.2},
        )
        replay = tmp_path / "replay.jsonl"
        replay.write_text(
            json.dumps({
                "run_id": "other-run",
                "iteration": 0,
                "timestamp": "2026-01-01T00:00:00Z",
                "symbol": "DEMO-SYMBOL",
                "mode": "paper",
                "data_source": "data/sample/ohlcv.csv",
                "strategy_id": "buy_and_hold",
                "proposed_action": "buy",
                "risk_result": {"status": "allowed", "allowed": True},
                "decision_state": "paper_executed",
            })
            + "\n",
            encoding="utf-8",
        )
        scorecard = build_autonomous_paper_scorecard(
            result.decisions_path,
            result.manifest_path,
            replay_decisions_path=str(replay),
        )
        assert scorecard["promotion_state"] == "blocked"
        assert scorecard["scorecard_dimensions"]["replay_determinism"]["passed"] is False

    def test_unsafe_live_provider_broker_references_rejected(self, tmp_path: Path):
        decisions = tmp_path / "decisions.jsonl"
        manifest = tmp_path / "manifest.json"
        bad_decision = {
            "run_id": "r",
            "iteration": 0,
            "timestamp": "2026-01-01T00:00:00Z",
            "symbol": "DEMO-SYMBOL",
            "mode": "paper",
            "data_source": "data/sample/ohlcv.csv",
            "strategy_id": "buy_and_hold",
            "proposed_action": "hold",
            "risk_result": {"status": "not_applicable", "allowed": True},
            "decision_state": "no_trade",
            "blocked_reason": None,
            "notes": "live_trading_enabled flag checked",
        }
        decisions.write_text(json.dumps(bad_decision) + "\n", encoding="utf-8")
        manifest.write_text(
            json.dumps({
                "run_id": "r",
                "mode": "paper",
                "symbol": "DEMO-SYMBOL",
                "strategy_id": "buy_and_hold",
                "data_source": "data/sample/ohlcv.csv",
                "bars_processed": 1,
                "decisions": 1,
                "trades_executed": 0,
                "trades_blocked": 0,
                "no_trade_count": 1,
                "decisions_path": str(decisions),
                "manifest_path": str(manifest),
            }),
            encoding="utf-8",
        )
        scorecard = build_autonomous_paper_scorecard(str(decisions), str(manifest))
        assert scorecard["promotion_state"] == "blocked"
        assert scorecard["scorecard_dimensions"]["no_live_side_effects"]["passed"] is False

    def test_redaction_requirements_enforced(self, tmp_path: Path):
        decisions = tmp_path / "decisions.jsonl"
        manifest = tmp_path / "manifest.json"
        bad_decision = {
            "run_id": "r",
            "iteration": 0,
            "timestamp": "2026-01-01T00:00:00Z",
            "symbol": "DEMO-SYMBOL",
            "mode": "paper",
            "data_source": "data/sample/ohlcv.csv",
            "strategy_id": "buy_and_hold",
            "proposed_action": "hold",
            "risk_result": {"status": "not_applicable", "allowed": True, "secret_token": "abc123"},
            "decision_state": "no_trade",
            "blocked_reason": None,
        }
        decisions.write_text(json.dumps(bad_decision) + "\n", encoding="utf-8")
        manifest.write_text(
            json.dumps({
                "run_id": "r",
                "mode": "paper",
                "symbol": "DEMO-SYMBOL",
                "strategy_id": "buy_and_hold",
                "data_source": "data/sample/ohlcv.csv",
                "bars_processed": 1,
                "decisions": 1,
                "trades_executed": 0,
                "trades_blocked": 0,
                "no_trade_count": 1,
                "decisions_path": str(decisions),
                "manifest_path": str(manifest),
            }),
            encoding="utf-8",
        )
        scorecard = build_autonomous_paper_scorecard(str(decisions), str(manifest))
        assert scorecard["promotion_state"] == "blocked"
        assert scorecard["scorecard_dimensions"]["audit_redaction"]["passed"] is False

    def test_promotion_state_conservative_defaults(self):
        scorecard = build_autonomous_paper_scorecard("", "")
        assert scorecard["promotion_state"] == "not_evaluated"


class TestAutonomousPaperScorecardRendering:
    def test_markdown_contains_required_sections(self, tmp_path: Path):
        config = _make_config(tmp_path)
        result = run_autonomous_paper_loop(
            config=config,
            max_cycles=2,
            strategy_id="buy_and_hold",
            strategy_parameters={"position_pct": 0.2},
        )
        scorecard = _scorecard_for_run(result)
        md = render_autonomous_paper_scorecard_markdown(scorecard)
        assert "Autonomous Paper Scorecard" in md
        assert "Safety flags" in md
        assert "Scorecard dimensions" in md
        assert "Promotion state" in md
        assert "Blockers" in md
        assert "not live-trading readiness" in md
