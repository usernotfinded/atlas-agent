# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/research/test_research_backtest_bridge.py
# PURPOSE: Verifies the research-to-backtest bridge derives only what an
#         artifact actually states, and authorizes nothing.
# DEPS:    json, pathlib, pytest, atlas_agent.
# ==============================================================================

"""Tests for the research artifact to backtest proposal bridge.

A research artifact is untrusted input. These tests pin what it may influence
(symbol, registered strategy, validated parameters) and what it may not.
"""

# --- IMPORTS ---

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from atlas_agent.research.backtest_bridge import (
    HYPOTHESIS_METADATA_KEY,
    STATUS_HYPOTHESIS_MALFORMED,
    STATUS_NO_HYPOTHESIS,
    STATUS_PROPOSED,
    build_backtest_proposal,
)
from atlas_agent.research.session import ResearchSessionError


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _write_artifact(
    workspace: Path,
    *,
    run_id: str = "run-0001",
    symbol: str = "AAPL",
    metadata: dict[str, Any] | None = None,
    omit_symbol: bool = False,
) -> Path:
    """Write a minimal research artifact to the workspace research directory."""
    research_dir = workspace / ".atlas" / "research" / symbol
    research_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": "1",
        "run_id": run_id,
        "symbol": symbol,
        "created_at": "2026-07-26T00:00:00+00:00",
        "provider": "deterministic",
        "summary": "Local deterministic context.",
        "thesis": "No directional thesis.",
        "risks": [],
        "warnings": [],
    }
    if omit_symbol:
        payload.pop("symbol")
    if metadata is not None:
        payload["metadata"] = metadata
    path = research_dir / f"{run_id}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _hypothesis(**fields: Any) -> dict[str, Any]:
    return {HYPOTHESIS_METADATA_KEY: fields}


class TestArtifactResolution:
    def test_missing_artifact_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ResearchSessionError, match="artifact_not_found"):
            build_backtest_proposal(tmp_path, "run-does-not-exist")

    def test_unsafe_run_id_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ResearchSessionError):
            build_backtest_proposal(tmp_path, "../escape")

    def test_artifact_without_symbol_is_malformed(self, tmp_path: Path) -> None:
        _write_artifact(tmp_path, omit_symbol=True)
        with pytest.raises(ResearchSessionError, match="artifact_malformed"):
            build_backtest_proposal(tmp_path, "run-0001")

    def test_symbol_is_taken_from_the_artifact_and_normalized(self, tmp_path: Path) -> None:
        _write_artifact(tmp_path, symbol="aapl")
        proposal = build_backtest_proposal(tmp_path, "run-0001")
        assert proposal["symbol"] == "AAPL"
        assert proposal["source_run_id"] == "run-0001"
        assert proposal["source_artifact_path"].endswith("run-0001.json")


class TestNoFabrication:
    """The bridge reports absence rather than inventing a hypothesis."""

    def test_artifact_without_metadata_proposes_nothing(self, tmp_path: Path) -> None:
        _write_artifact(tmp_path)
        proposal = build_backtest_proposal(tmp_path, "run-0001")

        assert proposal["status"] == STATUS_NO_HYPOTHESIS
        assert proposal["hypothesis_present"] is False
        assert proposal["accepted_strategies"] == []
        assert proposal["notes"]

    def test_prose_naming_a_strategy_is_not_a_hypothesis(self, tmp_path: Path) -> None:
        _write_artifact(
            tmp_path,
            metadata={"source": "deterministic"},
        )
        path = tmp_path / ".atlas" / "research" / "AAPL" / "run-0001.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["thesis"] = "A moving average cross over a short window looks promising."
        path.write_text(json.dumps(payload), encoding="utf-8")

        proposal = build_backtest_proposal(tmp_path, "run-0001")

        assert proposal["status"] == STATUS_NO_HYPOTHESIS
        assert proposal["accepted_strategies"] == []

    def test_non_object_hypothesis_is_ignored(self, tmp_path: Path) -> None:
        _write_artifact(tmp_path, metadata={HYPOTHESIS_METADATA_KEY: "moving_average_cross"})
        proposal = build_backtest_proposal(tmp_path, "run-0001")

        assert proposal["status"] == STATUS_NO_HYPOTHESIS
        assert proposal["accepted_strategies"] == []
        assert any("not an object" in note for note in proposal["notes"])


class TestStrategyValidation:
    def test_registered_strategy_is_accepted_with_defaults(self, tmp_path: Path) -> None:
        _write_artifact(tmp_path, metadata=_hypothesis(strategies=["buy_and_hold"]))
        proposal = build_backtest_proposal(tmp_path, "run-0001")

        assert proposal["status"] == STATUS_PROPOSED
        assert [item["strategy_id"] for item in proposal["accepted_strategies"]] == [
            "buy_and_hold"
        ]
        entry = proposal["accepted_strategies"][0]
        assert entry["parameters_supplied"] is False
        assert entry["display_name"]

    def test_supplied_parameters_are_coerced(self, tmp_path: Path) -> None:
        _write_artifact(
            tmp_path,
            metadata=_hypothesis(
                strategies=["moving_average_cross"],
                parameters={"moving_average_cross": {"short_window": "5", "long_window": 20}},
            ),
        )
        proposal = build_backtest_proposal(tmp_path, "run-0001")

        entry = proposal["accepted_strategies"][0]
        assert entry["parameters"]["short_window"] == 5
        assert entry["parameters"]["long_window"] == 20
        assert entry["parameters_supplied"] is True
        # Unstated parameters fall back to the strategy's own defaults.
        assert entry["parameters"]["exit_on_cross"] is True

    def test_unregistered_strategy_is_rejected_not_dropped(self, tmp_path: Path) -> None:
        _write_artifact(tmp_path, metadata=_hypothesis(strategies=["make_money_fast"]))
        proposal = build_backtest_proposal(tmp_path, "run-0001")

        assert proposal["accepted_strategies"] == []
        assert proposal["status"] == STATUS_HYPOTHESIS_MALFORMED
        rejected = proposal["rejected_strategies"]
        assert len(rejected) == 1
        assert rejected[0]["strategy_id"] == "make_money_fast"
        assert rejected[0]["reason_code"] == "unknown_strategy"

    def test_out_of_range_parameter_is_rejected(self, tmp_path: Path) -> None:
        _write_artifact(
            tmp_path,
            metadata=_hypothesis(
                strategies=["moving_average_cross"],
                parameters={"moving_average_cross": {"short_window": 0}},
            ),
        )
        proposal = build_backtest_proposal(tmp_path, "run-0001")

        assert proposal["accepted_strategies"] == []
        rejected = proposal["rejected_strategies"][0]
        assert rejected["reason_code"] == "invalid_parameters"
        assert "short_window" in rejected["reason"]

    def test_unknown_parameter_name_is_rejected_for_a_known_strategy(
        self, tmp_path: Path
    ) -> None:
        """A plausible-looking name the strategy does not define must not pass."""
        _write_artifact(
            tmp_path,
            metadata=_hypothesis(
                strategies=["moving_average_cross"],
                parameters={"moving_average_cross": {"fast_period": 5}},
            ),
        )
        proposal = build_backtest_proposal(tmp_path, "run-0001")

        assert proposal["accepted_strategies"] == []
        rejected = proposal["rejected_strategies"][0]
        assert rejected["reason_code"] == "invalid_parameters"
        assert "fast_period" in rejected["reason"]

    def test_unknown_parameter_is_rejected(self, tmp_path: Path) -> None:
        _write_artifact(
            tmp_path,
            metadata=_hypothesis(
                strategies=["buy_and_hold"],
                parameters={"buy_and_hold": {"leverage": 10}},
            ),
        )
        proposal = build_backtest_proposal(tmp_path, "run-0001")

        assert proposal["accepted_strategies"] == []
        rejected = proposal["rejected_strategies"][0]
        assert rejected["reason_code"] == "invalid_parameters"
        assert "leverage" in rejected["reason"]

    def test_malformed_entries_are_rejected_individually(self, tmp_path: Path) -> None:
        _write_artifact(
            tmp_path,
            metadata=_hypothesis(strategies=["buy_and_hold", 7, "", "buy_and_hold"]),
        )
        proposal = build_backtest_proposal(tmp_path, "run-0001")

        assert [item["strategy_id"] for item in proposal["accepted_strategies"]] == [
            "buy_and_hold"
        ]
        codes = sorted(item["reason_code"] for item in proposal["rejected_strategies"])
        assert codes == ["duplicate_strategy", "malformed_entry", "malformed_entry"]

    def test_non_object_parameter_block_is_rejected(self, tmp_path: Path) -> None:
        _write_artifact(
            tmp_path,
            metadata=_hypothesis(
                strategies=["buy_and_hold"],
                parameters={"buy_and_hold": ["fast_period", 5]},
            ),
        )
        proposal = build_backtest_proposal(tmp_path, "run-0001")

        assert proposal["accepted_strategies"] == []
        assert proposal["rejected_strategies"][0]["reason_code"] == "invalid_parameters"


class TestUnsupportedFields:
    def test_unsupported_hypothesis_fields_are_reported(self, tmp_path: Path) -> None:
        """An artifact must not be able to set anything outside the whitelist."""
        _write_artifact(
            tmp_path,
            metadata={
                HYPOTHESIS_METADATA_KEY: {
                    "strategies": ["buy_and_hold"],
                    "mode": "live",
                    "risk_enabled": False,
                    "kill_switch_state": True,
                }
            },
        )
        proposal = build_backtest_proposal(tmp_path, "run-0001")

        note = " ".join(proposal["notes"])
        assert "mode" in note
        assert "risk_enabled" in note
        assert "kill_switch_state" in note
        assert proposal["mode"] == "paper"
        assert "mode" not in proposal["accepted_strategies"][0]


class TestSafetyBoundary:
    def test_proposal_declares_no_execution_authority(self, tmp_path: Path) -> None:
        _write_artifact(tmp_path, metadata=_hypothesis(strategies=["buy_and_hold"]))
        proposal = build_backtest_proposal(tmp_path, "run-0001")

        safety = proposal["safety"]
        assert safety["creates_pending_orders"] is False
        assert safety["creates_approvals"] is False
        assert safety["submits_broker_orders"] is False
        assert safety["provider_required"] is False
        assert safety["broker_required"] is False
        assert safety["network_required"] is False
        assert safety["live_readiness"] is False
        assert safety["not_financial_advice"] is True

    def test_bridge_writes_nothing(self, tmp_path: Path) -> None:
        _write_artifact(tmp_path, metadata=_hypothesis(strategies=["buy_and_hold"]))
        before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))

        build_backtest_proposal(tmp_path, "run-0001")

        after = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
        assert after == before

    def test_source_artifact_is_not_modified(self, tmp_path: Path) -> None:
        path = _write_artifact(tmp_path, metadata=_hypothesis(strategies=["buy_and_hold"]))
        before = path.read_bytes()

        build_backtest_proposal(tmp_path, "run-0001")

        assert path.read_bytes() == before
