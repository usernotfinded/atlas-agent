"""Integration tests for the stateful autonomous paper runner.

These tests exercise the full stateful paper workflow end-to-end, verifying
that state persists across invocations, resumes advance the cursor, duplicate
bars are skipped, and artifacts remain redacted and portable.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from atlas_agent.agent.autonomous_paper import run_stateful_autonomous_paper_loop
from atlas_agent.config import AtlasConfig


SAMPLE_CSV = Path(__file__).resolve().parents[1] / "data" / "sample" / "ohlcv.csv"


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


def test_stateful_paper_loop_persists_state_and_resumes(tmp_path: Path):
    atlas_config = _make_config(tmp_path)
    state_dir = tmp_path / "state"
    output_dir = tmp_path / "output"
    run_id = "integration-run-001"

    first = run_stateful_autonomous_paper_loop(
        config=atlas_config,
        symbol="DEMO-SYMBOL",
        strategy_id="buy_and_hold",
        strategy_parameters={"position_pct": 0.2},
        data_path=atlas_config.backtest.data_path,
        max_cycles=2,
        state_dir=state_dir,
        output_dir=output_dir,
        run_id=run_id,
        fill_timing="same_bar",
    )
    assert first.status == "completed"
    assert first.bars_processed_this_run == 2

    state_files = list(state_dir.glob("*-state.json"))
    checkpoint_files = list(state_dir.glob("*-checkpoint.json"))
    assert state_files, "state file should be persisted"
    assert checkpoint_files, "checkpoint file should be persisted"

    second = run_stateful_autonomous_paper_loop(
        config=atlas_config,
        symbol="DEMO-SYMBOL",
        strategy_id="buy_and_hold",
        strategy_parameters={"position_pct": 0.2},
        data_path=atlas_config.backtest.data_path,
        max_cycles=2,
        state_dir=state_dir,
        output_dir=output_dir,
        resume=True,
        run_id=run_id,
        fill_timing="same_bar",
    )
    assert second.status == "completed"
    assert second.run_id == run_id
    assert second.total_bars_processed == 4
    assert second.bars_processed_this_run == 2


def test_stateful_paper_loop_artifacts_are_redacted(tmp_path: Path):
    atlas_config = _make_config(tmp_path)
    state_dir = tmp_path / "state"
    output_dir = tmp_path / "output"
    run_id = "integration-run-redact"

    result = run_stateful_autonomous_paper_loop(
        config=atlas_config,
        symbol="DEMO-SYMBOL",
        strategy_id="buy_and_hold",
        strategy_parameters={"position_pct": 0.2},
        data_path=atlas_config.backtest.data_path,
        max_cycles=2,
        state_dir=state_dir,
        output_dir=output_dir,
        run_id=run_id,
    )
    assert result.status == "completed"

    state_path = state_dir / f"{run_id}-state.json"
    state_text = state_path.read_text(encoding="utf-8")
    assert str(Path.home()) not in state_text
    assert "/Users/" not in state_text

    manifest_path = Path(result.manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key in ("decisions_path", "fills_path", "metrics_path", "checkpoint_path"):
        value = manifest.get(key, "")
        assert not value.startswith("/"), f"{key} must be a relative path"
