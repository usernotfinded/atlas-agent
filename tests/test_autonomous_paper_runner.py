from __future__ import annotations

import json
import shutil
from pathlib import Path

from atlas_agent.agent.autonomous_paper import run_stateful_autonomous_paper_loop
from atlas_agent.agent.autonomous_paper_models import (
    StatefulPaperConfig,
    StatefulPaperState,
)
from atlas_agent.agent.autonomous_paper_runner import (
    _bar_hash,
    _state_path,
    load_state_or_initialize,
    run_stateful_autonomous_paper,
    save_state,
)
from atlas_agent.backtest.data import load_market_data
from atlas_agent.config import AtlasConfig
from atlas_agent.safety.kill_switch import KillSwitchController

import pytest

SAMPLE_CSV = Path(__file__).resolve().parents[1] / "data" / "sample" / "ohlcv.csv"


def _read_fills(fills_path: str | Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in Path(fills_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


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


def _make_stateful_config(
    atlas_config: AtlasConfig,
    tmp_path: Path,
    run_id: str = "stateful-run-001",
    **overrides: object,
) -> StatefulPaperConfig:
    kwargs: dict[str, object] = {
        "run_id": run_id,
        "symbol": atlas_config.market.symbol or "DEMO-SYMBOL",
        "strategy_id": "buy_and_hold",
        "strategy_parameters": {"position_pct": 0.2},
        "data_path": str(atlas_config.backtest.data_path),
        "output_dir": str(tmp_path / "output"),
        "state_dir": str(tmp_path / "state"),
        "initial_cash": atlas_config.backtest.initial_cash,
    }
    kwargs.update(overrides)
    return StatefulPaperConfig.model_validate(kwargs)


def test_runner_initializes_state_on_first_run(tmp_path: Path):
    atlas_config = _make_config(tmp_path)
    config = _make_stateful_config(atlas_config, tmp_path)
    result = run_stateful_autonomous_paper(
        config=config,
        atlas_config=atlas_config,
        max_cycles=2,
    )
    assert result.status == "completed"
    assert result.bars_processed_this_run == 2
    state_path = _state_path(config.state_dir, config.run_id)
    assert state_path.exists()
    state = StatefulPaperState.model_validate(
        json.loads(state_path.read_text(encoding="utf-8"))
    )
    assert state.cursor.last_processed_bar_index == 1
    assert len(state.cursor.processed_bar_hashes) == 2


def test_runner_resumes_from_cursor(tmp_path: Path):
    atlas_config = _make_config(tmp_path)
    config = _make_stateful_config(atlas_config, tmp_path)
    result1 = run_stateful_autonomous_paper(
        config=config,
        atlas_config=atlas_config,
        max_cycles=2,
    )
    assert result1.status == "completed"
    initial_total_bars = result1.total_bars_processed
    initial_fills = result1.metrics.number_of_fills if result1.metrics else 0

    result2 = run_stateful_autonomous_paper(
        config=config,
        atlas_config=atlas_config,
        resume=True,
        max_cycles=2,
    )
    assert result2.status == "completed"
    assert result2.total_bars_processed == initial_total_bars + 2
    assert (
        result2.metrics.number_of_fills if result2.metrics else -1
    ) == initial_fills
    state_path = _state_path(config.state_dir, config.run_id)
    state = StatefulPaperState.model_validate(
        json.loads(state_path.read_text(encoding="utf-8"))
    )
    assert state.cursor.last_processed_bar_index == 3


def test_runner_does_not_reprocess_duplicate_bars(tmp_path: Path):
    atlas_config = _make_config(tmp_path)
    config = _make_stateful_config(atlas_config, tmp_path)
    bars = load_market_data(config.data_path, symbol=config.symbol)
    first_bar_hash = _bar_hash(bars[0])

    state = load_state_or_initialize(
        state_dir=config.state_dir,
        run_id=config.run_id,
        config=config,
    )
    state.cursor.processed_bar_hashes.append(first_bar_hash)
    save_state(state, config.state_dir)

    result = run_stateful_autonomous_paper(
        config=config,
        atlas_config=atlas_config,
        resume=True,
        max_cycles=3,
    )
    assert result.status == "completed"
    assert result.bars_processed_this_run == 2
    state_path = _state_path(config.state_dir, config.run_id)
    state = StatefulPaperState.model_validate(
        json.loads(state_path.read_text(encoding="utf-8"))
    )
    assert state.cursor.last_processed_bar_index == 2
    assert first_bar_hash in state.cursor.processed_bar_hashes


def test_runner_returns_no_new_data_cleanly(tmp_path: Path):
    atlas_config = _make_config(tmp_path)
    config = _make_stateful_config(atlas_config, tmp_path)
    result1 = run_stateful_autonomous_paper(
        config=config,
        atlas_config=atlas_config,
        max_cycles=0,
    )
    assert result1.status == "completed"
    total_bars = result1.total_bars_processed

    result2 = run_stateful_autonomous_paper(
        config=config,
        atlas_config=atlas_config,
        resume=True,
        max_cycles=0,
    )
    assert result2.status == "no_new_data"
    assert result2.bars_processed_this_run == 0
    assert result2.total_bars_processed == total_bars


def test_runner_malformed_state_fails_closed(tmp_path: Path):
    atlas_config = _make_config(tmp_path)
    config = _make_stateful_config(atlas_config, tmp_path)
    state_path = _state_path(config.state_dir, config.run_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("not valid json", encoding="utf-8")

    result = run_stateful_autonomous_paper(
        config=config,
        atlas_config=atlas_config,
        resume=True,
        max_cycles=2,
    )
    assert result.status == "failed"
    assert any("malformed_state" in e.lower() for e in result.errors)


def test_runner_state_mismatch_fails_closed(tmp_path: Path):
    atlas_config = _make_config(tmp_path)
    config = _make_stateful_config(atlas_config, tmp_path)
    result1 = run_stateful_autonomous_paper(
        config=config,
        atlas_config=atlas_config,
        max_cycles=2,
    )
    assert result1.status == "completed"

    config2 = _make_stateful_config(
        atlas_config, tmp_path, run_id=config.run_id, symbol="OTHER"
    )
    result2 = run_stateful_autonomous_paper(
        config=config2,
        atlas_config=atlas_config,
        resume=True,
        max_cycles=2,
    )
    assert result2.status == "failed"
    assert any("state_mismatch" in e.lower() for e in result2.errors)


def test_runner_kill_switch_blocks(tmp_path: Path):
    atlas_config = _make_config(tmp_path)
    config = _make_stateful_config(atlas_config, tmp_path)
    controller = KillSwitchController(
        state_path=atlas_config.memory_dir / "kill_switch_state.json",
        enabled_flag_path=atlas_config.memory_dir / "kill_switch.enabled",
    )
    controller.enable(mode="soft", reason="test", actor="test")

    result = run_stateful_autonomous_paper(
        config=config,
        atlas_config=atlas_config,
        max_cycles=2,
        kill_switch=controller,
    )
    assert result.status == "blocked"
    assert result.bars_processed_this_run == 0
    fills = _read_fills(Path(config.output_dir) / f"{config.run_id}-fills.jsonl")
    assert len(fills) == 0


def test_runner_malformed_state_error_is_redacted(tmp_path: Path):
    atlas_config = _make_config(tmp_path)
    config = _make_stateful_config(atlas_config, tmp_path)
    state_path = _state_path(config.state_dir, config.run_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("not valid json", encoding="utf-8")

    result = run_stateful_autonomous_paper(
        config=config,
        atlas_config=atlas_config,
        resume=True,
        max_cycles=2,
    )
    assert result.status == "failed"
    assert result.errors
    error = result.errors[0]
    assert error.startswith("malformed_state:")
    assert "/Users/" not in error
    assert "/tmp/" not in error
    assert "Traceback" not in error
    assert "JSONDecodeError" not in error


def test_runner_data_load_error_is_redacted(tmp_path: Path):
    atlas_config = _make_config(tmp_path)
    config = _make_stateful_config(
        atlas_config, tmp_path, data_path=str(tmp_path / "missing.csv")
    )

    result = run_stateful_autonomous_paper(
        config=config,
        atlas_config=atlas_config,
        max_cycles=2,
    )
    assert result.status == "failed"
    assert result.errors
    error = result.errors[0]
    assert "/Users/" not in error
    assert str(tmp_path) not in error
    assert "Traceback" not in error


def test_wrapper_kill_switch_blocks(tmp_path: Path):
    atlas_config = _make_config(tmp_path)
    controller = KillSwitchController(
        state_path=atlas_config.memory_dir / "kill_switch_state.json",
        enabled_flag_path=atlas_config.memory_dir / "kill_switch.enabled",
    )
    controller.enable(mode="soft", reason="test", actor="test")

    result = run_stateful_autonomous_paper_loop(
        config=atlas_config,
        symbol="DEMO-SYMBOL",
        strategy_id="buy_and_hold",
        strategy_parameters={"position_pct": 0.2},
        state_dir=tmp_path / "state",
        output_dir=tmp_path / "output",
        max_cycles=2,
        kill_switch=controller,
    )
    assert result.status == "blocked"


def test_wrapper_entry_point_returns_result(tmp_path: Path):
    atlas_config = _make_config(tmp_path)
    result = run_stateful_autonomous_paper_loop(
        config=atlas_config,
        symbol="DEMO-SYMBOL",
        strategy_id="buy_and_hold",
        strategy_parameters={"position_pct": 0.2},
        state_dir=tmp_path / "state",
        output_dir=tmp_path / "output",
        max_cycles=2,
    )
    assert result.status == "completed"
    assert result.bars_processed_this_run == 2
    assert Path(result.checkpoint_path).exists()


def test_runner_next_bar_fill_uses_later_price(tmp_path: Path):
    atlas_config = _make_config(tmp_path)
    config = _make_stateful_config(
        atlas_config,
        tmp_path,
        fill_timing="next_bar",
        commission_bps=0.0,
        slippage_bps=0.0,
        strategy_parameters={"position_pct": 0.2},
    )
    result = run_stateful_autonomous_paper(
        config=config,
        atlas_config=atlas_config,
        max_cycles=2,
    )
    assert result.status == "completed"
    fills = _read_fills(Path(config.output_dir) / f"{config.run_id}-fills.jsonl")
    assert len(fills) == 1
    bars = load_market_data(config.data_path, symbol=config.symbol)
    assert fills[0]["price"] == pytest.approx(bars[1].close)


def test_runner_avoids_same_bar_lookahead(tmp_path: Path):
    atlas_config = _make_config(tmp_path)
    config = _make_stateful_config(
        atlas_config,
        tmp_path,
        fill_timing="next_bar",
        commission_bps=0.0,
        slippage_bps=0.0,
        strategy_parameters={"position_pct": 0.2},
    )
    result = run_stateful_autonomous_paper(
        config=config,
        atlas_config=atlas_config,
        max_cycles=2,
    )
    assert result.status == "completed"
    fills = _read_fills(Path(config.output_dir) / f"{config.run_id}-fills.jsonl")
    assert len(fills) == 1
    bars = load_market_data(config.data_path, symbol=config.symbol)
    assert fills[0]["price"] != pytest.approx(bars[0].close)


def test_runner_commission_reduces_ending_cash(tmp_path: Path):
    atlas_config = _make_config(tmp_path)
    base_config = _make_stateful_config(
        atlas_config,
        tmp_path,
        run_id="base-run",
        fill_timing="same_bar",
        commission_bps=0.0,
        slippage_bps=0.0,
        strategy_parameters={"position_pct": 0.2},
    )
    base_result = run_stateful_autonomous_paper(
        config=base_config,
        atlas_config=atlas_config,
        max_cycles=2,
    )
    assert base_result.metrics is not None

    comm_config = _make_stateful_config(
        atlas_config,
        tmp_path,
        run_id="comm-run",
        fill_timing="same_bar",
        commission_bps=10.0,
        slippage_bps=0.0,
        strategy_parameters={"position_pct": 0.2},
    )
    comm_result = run_stateful_autonomous_paper(
        config=comm_config,
        atlas_config=atlas_config,
        max_cycles=2,
    )
    assert comm_result.metrics is not None

    assert comm_result.metrics.ending_cash < base_result.metrics.ending_cash
    assert comm_result.metrics.ending_equity < base_result.metrics.ending_equity


def test_runner_slippage_changes_fill_price(tmp_path: Path):
    atlas_config = _make_config(tmp_path)
    config = _make_stateful_config(
        atlas_config,
        tmp_path,
        fill_timing="same_bar",
        commission_bps=0.0,
        slippage_bps=10.0,
        strategy_parameters={"position_pct": 0.2},
    )
    result = run_stateful_autonomous_paper(
        config=config,
        atlas_config=atlas_config,
        max_cycles=1,
    )
    assert result.status == "completed"
    fills = _read_fills(Path(config.output_dir) / f"{config.run_id}-fills.jsonl")
    assert len(fills) == 1
    bars = load_market_data(config.data_path, symbol=config.symbol)
    assert fills[0]["price"] != pytest.approx(bars[0].close)


def test_runner_writes_metrics_file_with_expected_keys(tmp_path: Path):
    atlas_config = _make_config(tmp_path)
    config = _make_stateful_config(atlas_config, tmp_path)
    result = run_stateful_autonomous_paper(
        config=config,
        atlas_config=atlas_config,
        max_cycles=2,
    )
    assert result.status == "completed"
    assert result.metrics is not None

    metrics_path = Path(config.output_dir) / f"{config.run_id}-metrics.json"
    assert metrics_path.exists()
    data = json.loads(metrics_path.read_text(encoding="utf-8"))
    for key in (
        "starting_cash",
        "ending_cash",
        "ending_equity",
        "total_return_pct",
        "max_drawdown_pct",
        "number_of_trades",
        "number_of_fills",
        "number_of_rejections",
        "gross_exposure",
        "net_exposure",
        "bars_processed",
        "generated_at",
        "notes",
    ):
        assert key in data, f"missing metric key: {key}"


def test_runner_corrupted_checkpoint_fails_closed(tmp_path: Path):
    atlas_config = _make_config(tmp_path)
    config = _make_stateful_config(atlas_config, tmp_path)
    first = run_stateful_autonomous_paper(
        config=config,
        atlas_config=atlas_config,
        max_cycles=2,
    )
    assert first.status == "completed"

    state_path = _state_path(config.state_dir, config.run_id)
    checkpoint_path = Path(config.state_dir) / f"{config.run_id}-checkpoint.json"
    assert checkpoint_path.exists()
    state_path.unlink()

    # Corrupt the checkpoint JSON by truncating it.
    raw = checkpoint_path.read_text(encoding="utf-8")
    checkpoint_path.write_text(raw[: len(raw) // 2], encoding="utf-8")

    result = run_stateful_autonomous_paper(
        config=config,
        atlas_config=atlas_config,
        resume=True,
        max_cycles=2,
    )
    assert result.status == "failed"
    assert any("corrupted_checkpoint" in e.lower() for e in result.errors)


def _read_decisions(decisions_path: str | Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in Path(decisions_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _strip_non_deterministic(decisions: list[dict], fills: list[dict]) -> tuple[list, list]:
    """Remove audit event ids and run-specific paths from decisions/fills."""
    clean_decisions = []
    for d in decisions:
        d = dict(d)
        d.pop("audit_event_ids", None)
        clean_decisions.append(d)
    clean_fills = []
    for f in fills:
        f = dict(f)
        f.pop("fill_id", None)
        clean_fills.append(f)
    return clean_decisions, clean_fills


def test_runner_deterministic_replay(tmp_path: Path):
    run_id = "replay-run-001"

    def run(root: Path):
        atlas_config = _make_config(root)
        config = _make_stateful_config(
            atlas_config,
            root,
            run_id=run_id,
            fill_timing="same_bar",
            commission_bps=0.0,
            slippage_bps=0.0,
            strategy_parameters={"position_pct": 0.2},
        )
        result = run_stateful_autonomous_paper(
            config=config,
            atlas_config=atlas_config,
            max_cycles=3,
        )
        assert result.status == "completed"
        decisions = _read_decisions(
            Path(config.output_dir) / f"{config.run_id}-decisions.jsonl"
        )
        fills = _read_fills(Path(config.output_dir) / f"{config.run_id}-fills.jsonl")
        return decisions, fills

    decisions_a, fills_a = run(tmp_path / "a")
    decisions_b, fills_b = run(tmp_path / "b")

    decisions_a, fills_a = _strip_non_deterministic(decisions_a, fills_a)
    decisions_b, fills_b = _strip_non_deterministic(decisions_b, fills_b)

    assert decisions_a == decisions_b
    assert fills_a == fills_b


def test_runner_does_not_import_brokers_or_providers():
    source = Path("src/atlas_agent/agent/autonomous_paper_runner.py").read_text()
    forbidden = [
        "atlas_agent.brokers",
        "atlas_agent.providers",
        "atlas_agent.execution.live",
    ]
    for pattern in forbidden:
        assert pattern not in source, f"Forbidden reference in runner: {pattern}"
