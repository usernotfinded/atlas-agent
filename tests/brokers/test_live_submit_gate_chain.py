# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/brokers/test_live_submit_gate_chain.py
# PURPOSE: Asserts each live-submit gate blocks on its own, and that the chain
#         can reach ready when every gate is satisfied.
# DEPS:    json, os, pathlib, datetime, pytest, atlas_agent.
# ==============================================================================

"""Per-gate coverage for `BrokerResolver._resolve_can_submit`.

The governance document states that `can_submit` is false unless every opt-in
gate is satisfied. Eight gates all deny by default, which means a test that
leaves the defaults in place proves almost nothing: were one gate to stop
denying, the others would still return False and every such test would keep
passing.

These cases therefore satisfy the whole chain and then break exactly one gate
at a time, so each gate is shown to carry its own weight. The positive case
pins the other half of the claim — that a fully satisfied chain does reach
ready — which nothing asserted before.
"""

# --- IMPORTS ---

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from atlas_agent.brokers.resolver import (
    BrokerResolver,
    _compute_live_submit_fingerprint,
)
from atlas_agent.config import AtlasConfig


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

@pytest.fixture
def live_ready_config(tmp_path: Path, monkeypatch) -> AtlasConfig:
    """A config with all eight live-submit gates satisfied."""
    config = AtlasConfig(
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending_orders",
        reports_dir=tmp_path / "reports",
        events_dir=tmp_path / "events",
        data_path=tmp_path / "data" / "ohlcv.csv",
        workspace_root=tmp_path,
    )
    config.ensure_dirs()

    config.broker.provider = "alpaca"
    config.broker.enable_live_submit = True
    config.broker.enable_live_trading = True
    config.trading_mode = "live"
    config.safety.order_approval_mode = "manual_live"
    config.risk.allow_leverage = False

    monkeypatch.setenv("ALPACA_API_KEY", "test-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")

    _write_opt_in(config)
    return config


def _write_opt_in(config: AtlasConfig) -> None:
    """Write a currently-valid live-submit opt-in record."""
    record = {
        "event_type": "live_submit_opt_in_enabled",
        "opt_in": True,
        "broker_id": config.broker.provider,
        "config_fingerprint": _compute_live_submit_fingerprint(config),
        "created_at": datetime.now(UTC).isoformat(),
    }
    path = Path(config.audit_dir) / "live_submit_opt_in.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")


def _can_submit(config: AtlasConfig) -> tuple[bool, str]:
    resolver = BrokerResolver(config)
    allowed, code, _message = resolver._resolve_can_submit(config.broker.provider)
    return allowed, code


class TestChainReachesReady:
    def test_all_gates_satisfied_allows_submit(self, live_ready_config: AtlasConfig) -> None:
        """Without this, a permanently-false chain would look correct."""
        allowed, code = _can_submit(live_ready_config)
        assert allowed is True
        assert code == "live_submit_ready"


class TestEachGateBlocksAlone:
    """One gate broken at a time, everything else satisfied."""

    def test_live_submit_flag_off(self, live_ready_config: AtlasConfig) -> None:
        live_ready_config.broker.enable_live_submit = False
        assert _can_submit(live_ready_config) == (False, "live_submit_disabled")

    def test_live_trading_flag_off(self, live_ready_config: AtlasConfig) -> None:
        live_ready_config.broker.enable_live_trading = False
        assert _can_submit(live_ready_config) == (False, "live_trading_disabled")

    def test_trading_mode_not_live(self, live_ready_config: AtlasConfig) -> None:
        live_ready_config.trading_mode = "paper"
        assert _can_submit(live_ready_config) == (False, "trading_mode_not_live")

    def test_approval_mode_disables_live(self, live_ready_config: AtlasConfig) -> None:
        live_ready_config.safety.order_approval_mode = "disabled_live"
        assert _can_submit(live_ready_config) == (False, "approval_disabled")

    def test_leverage_enabled(self, live_ready_config: AtlasConfig) -> None:
        live_ready_config.risk.allow_leverage = True
        assert _can_submit(live_ready_config) == (False, "leverage_enabled")

    def test_credentials_missing(self, live_ready_config: AtlasConfig, monkeypatch) -> None:
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        assert _can_submit(live_ready_config) == (False, "credentials_missing")

    def test_opt_in_record_missing(self, live_ready_config: AtlasConfig) -> None:
        (Path(live_ready_config.audit_dir) / "live_submit_opt_in.jsonl").unlink()
        allowed, code = _can_submit(live_ready_config)
        assert allowed is False
        assert code == "opt_in_file_missing"

    def test_armed_kill_switch(self, live_ready_config: AtlasConfig) -> None:
        """An armed switch in a non-normal mode must stop live submit."""
        state_path = Path(live_ready_config.memory_dir) / "kill_switch_state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "enabled": True,
                    "mode": "soft",
                    "reason": "test",
                    "actor": "test",
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ),
            encoding="utf-8",
        )
        assert _can_submit(live_ready_config) == (False, "kill_switch_active")

    def test_unreadable_kill_switch_state_fails_closed(
        self, live_ready_config: AtlasConfig
    ) -> None:
        """A state file that cannot be read must deny, never default to normal."""
        state_path = Path(live_ready_config.memory_dir) / "kill_switch_state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text("{ not json", encoding="utf-8")

        allowed, code = _can_submit(live_ready_config)
        assert allowed is False
        assert code in {"kill_switch_active", "kill_switch_unreadable"}


class TestOptInRecordIsBoundToConfig:
    def test_opt_in_for_a_different_config_is_rejected(
        self, live_ready_config: AtlasConfig
    ) -> None:
        """An opt-in must not survive a change to the limits it was granted under."""
        live_ready_config.risk.max_order_notional = 999999.0

        allowed, code = _can_submit(live_ready_config)
        assert allowed is False
        assert code != "live_submit_ready"
