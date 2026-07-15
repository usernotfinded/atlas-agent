# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_autonomous_paper_redaction.py
# PURPOSE: Verifies autonomous paper redaction behavior and regression
#         expectations.
# DEPS:    json, shutil, pathlib, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from atlas_agent.agent.autonomous_paper_models import StatefulPaperState
from atlas_agent.agent.autonomous_paper_runner import (
    _state_path,
    load_state_or_initialize,
    run_stateful_autonomous_paper,
    save_state,
)
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


def _make_stateful_config(
    atlas_config: AtlasConfig,
    tmp_path: Path,
    run_id: str = "stateful-run-001",
    **overrides: object,
) -> "StatefulPaperConfig":
    from atlas_agent.agent.autonomous_paper_models import StatefulPaperConfig

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


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class TestStatefulPaperArtifactRedaction:
    def test_state_file_does_not_contain_home_directory(self, tmp_path: Path):
        atlas_config = _make_config(tmp_path)
        config = _make_stateful_config(atlas_config, tmp_path)
        result = run_stateful_autonomous_paper(
            config=config,
            atlas_config=atlas_config,
            max_cycles=2,
        )
        assert result.status == "completed"

        state_path = _state_path(config.state_dir, config.run_id)
        text = state_path.read_text(encoding="utf-8")
        home = str(Path.home())
        assert home not in text, "state file contains home directory"
        assert "/Users/" not in text, "state file contains /Users/ prefix"

    def test_metrics_file_uses_redacted_data_source(self, tmp_path: Path):
        atlas_config = _make_config(tmp_path)
        config = _make_stateful_config(atlas_config, tmp_path)
        result = run_stateful_autonomous_paper(
            config=config,
            atlas_config=atlas_config,
            max_cycles=2,
        )
        assert result.status == "completed"

        metrics_path = Path(config.output_dir) / f"{config.run_id}-metrics.json"
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
        assert data["data_source_redacted"] == "ohlcv.csv"
        assert "/" not in data["data_source_redacted"]

    def test_decisions_file_is_redacted(self, tmp_path: Path):
        atlas_config = _make_config(tmp_path)
        config = _make_stateful_config(atlas_config, tmp_path)
        result = run_stateful_autonomous_paper(
            config=config,
            atlas_config=atlas_config,
            max_cycles=2,
        )
        assert result.status == "completed"

        decisions_path = Path(config.output_dir) / f"{config.run_id}-decisions.jsonl"
        decisions = _load_jsonl(decisions_path)
        assert decisions
        text = decisions_path.read_text(encoding="utf-8")
        assert "/Users/" not in text
        assert str(Path.home()) not in text
        assert "/private/var/" not in text
        assert "/var/folders/" not in text

    def test_manifest_is_redacted(self, tmp_path: Path):
        atlas_config = _make_config(tmp_path)
        config = _make_stateful_config(atlas_config, tmp_path)
        result = run_stateful_autonomous_paper(
            config=config,
            atlas_config=atlas_config,
            max_cycles=2,
        )
        assert result.status == "completed"

        manifest_path = Path(config.output_dir) / f"{config.run_id}-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        for key in (
            "decisions_path",
            "fills_path",
            "metrics_path",
            "checkpoint_path",
            "manifest_path",
            "audit_log_path",
        ):
            value = manifest.get(key, "")
            assert not value.startswith("/"), f"{key} is an absolute path: {value!r}"

        text = manifest_path.read_text(encoding="utf-8")
        assert "/Users/" not in text
        assert str(Path.home()) not in text
        assert "/private/var/" not in text
        assert "/var/folders/" not in text

    def test_error_messages_are_redacted(self, tmp_path: Path):
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
        assert str(tmp_path) not in error
        assert "Traceback" not in error
        assert "JSONDecodeError" not in error


class TestSaveStateRedaction:
    def test_save_state_redacts_secrets_in_errors(self, tmp_path: Path):
        atlas_config = _make_config(tmp_path)
        config = _make_stateful_config(atlas_config, tmp_path)
        state = load_state_or_initialize(
            state_dir=config.state_dir,
            run_id=config.run_id,
            config=config,
        )
        state.errors.append("api_key=sk-live-abcdefghijklmnopqrstuvwxyz1234")
        save_state(state, config.state_dir)

        state_path = _state_path(config.state_dir, config.run_id)
        text = state_path.read_text(encoding="utf-8")
        assert "sk-live-abcdefghijklmnopqrstuvwxyz1234" not in text
