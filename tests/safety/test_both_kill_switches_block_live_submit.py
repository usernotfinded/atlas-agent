# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/safety/test_both_kill_switches_block_live_submit.py
# PURPOSE: Pins that either kill-switch surface blocks live submit, not just the
#         one the resolver happened to read.
# DEPS:    json, pathlib, datetime, pytest, atlas_agent.
# ==============================================================================

"""There are two kill switches, and the runbook documents the wrong one.

Atlas Agent ships two independent emergency stops:

- `KillSwitchController` — `atlas kill-switch {enable,disable,status}`, state in
  `memory/kill_switch_state.json`, modes `soft`/`cancel`/`flatten`. It performs
  the broker side effects, and `_resolve_can_submit` reads it.
- `AdvancedKillSwitch` — `atlas kill {soft-pause,cancel-all,flatten-all,lock}`,
  state in `.atlas/safety/kill_switch.json`, modes `soft_pause`/`cancel_all`/
  `flatten_all`/`locked_down`. It carries the dead-man heartbeat and the action
  planner.

They share no state. `docs/kill-switch.md` — the Kill Switch Runbook, the
document an operator reaches for in an emergency — documents only the second,
and `docs/cli-command-compatibility.md` lists both as current with neither
marked legacy. So the strongest command in the runbook, `atlas kill
flatten-all`, left `_resolve_can_submit` returning `live_submit_ready`: the
operator-facing emergency stop did not close the live path.

The fix follows the doctrine `cli_safety.py` already states for the other pair
of sources — "OR, never AND". Either switch armed means live submit is refused.
Unifying the two surfaces is a larger design question; blocking on both is the
part that cannot wait for it.

A failure here means one of the two documented emergency stops has gone quiet
again.
"""

# --- IMPORTS ---

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

pytestmark = pytest.mark.quick

# Every mode `atlas kill` can set that is not "normal". Each one is an operator
# saying stop; none of them may leave the live path open.
ADVANCED_STOP_MODES = ("soft_pause", "cancel_all", "flatten_all", "locked_down")


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

@pytest.fixture
def ready_to_submit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A workspace where live submit is genuinely open.

    Every gate ahead of the kill switch is satisfied on purpose. Without that
    the resolver refuses for some earlier reason and these cases would pass
    while proving nothing about either switch — the failure mode that has
    already caught four tests in this suite.
    """
    from atlas_agent.brokers.resolver import (
        BrokerResolver,
        _compute_live_submit_fingerprint,
    )
    from atlas_agent.config import AtlasConfig

    monkeypatch.setenv("ALPACA_API_KEY", "test-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")

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
    config.trading_mode = "live"
    config.broker.provider = "alpaca"
    config.broker.enable_live_submit = True
    config.broker.enable_live_trading = True

    record = {
        "event_type": "live_submit_opt_in_enabled",
        "opt_in": True,
        "broker_id": "alpaca",
        "created_at": datetime.now(UTC).isoformat(),
        "config_fingerprint": _compute_live_submit_fingerprint(config),
    }
    (Path(config.audit_dir) / "live_submit_opt_in.jsonl").write_text(
        json.dumps(record) + "\n", encoding="utf-8"
    )

    # The premise of every case below. If this ever stops holding, the cases are
    # no longer testing what they claim to.
    allowed, reason, _message = BrokerResolver(config)._resolve_can_submit("alpaca")
    assert (allowed, reason) == (True, "live_submit_ready")
    return config


def _advanced_switch(config):
    from atlas_agent.config.paths import get_safety_dir_for
    from atlas_agent.safety.kill_switch import AdvancedKillSwitch

    safety_dir = get_safety_dir_for(config)
    safety_dir.mkdir(parents=True, exist_ok=True)
    return AdvancedKillSwitch(
        state_path=safety_dir / "kill_switch.json",
        heartbeat_path=safety_dir / "heartbeat.json",
    )


@pytest.mark.parametrize("mode", ADVANCED_STOP_MODES)
def test_atlas_kill_modes_close_the_live_submit_path(ready_to_submit, mode: str) -> None:
    """`atlas kill <mode>` has to mean the live path is shut."""
    from atlas_agent.brokers.resolver import BrokerResolver

    _advanced_switch(ready_to_submit).set_mode(mode, reason="runbook", actor="user")

    allowed, reason, _message = BrokerResolver(ready_to_submit)._resolve_can_submit(
        "alpaca"
    )

    assert allowed is False
    assert reason == "kill_switch_active"


def test_atlas_kill_switch_enable_still_closes_the_live_submit_path(
    ready_to_submit,
) -> None:
    """The surface that already worked keeps working.

    Reading a second source must not become a replacement for the first.
    """
    from atlas_agent.brokers.resolver import BrokerResolver
    from atlas_agent.safety.kill_switch import KillSwitchController

    KillSwitchController(
        state_path=Path(ready_to_submit.memory_dir) / "kill_switch_state.json",
        enabled_flag_path=Path(ready_to_submit.memory_dir) / "kill_switch.enabled",
    ).enable(mode="soft", reason="operator halt", actor="cli", broker=None)

    allowed, reason, _message = BrokerResolver(ready_to_submit)._resolve_can_submit(
        "alpaca"
    )

    assert allowed is False
    assert reason == "kill_switch_active"


def test_an_unreadable_advanced_switch_fails_closed(ready_to_submit) -> None:
    """Not being able to read the second switch is not permission either.

    The first switch already answers `kill_switch_unreadable` here. The second
    has to fail the same way, or corrupting a file becomes a way to reopen the
    live path.
    """
    from atlas_agent.brokers.resolver import BrokerResolver

    from atlas_agent.config.paths import get_safety_dir_for

    safety_dir = get_safety_dir_for(ready_to_submit)
    safety_dir.mkdir(parents=True, exist_ok=True)
    (safety_dir / "kill_switch.json").write_text("{ not json", encoding="utf-8")

    allowed, reason, _message = BrokerResolver(ready_to_submit)._resolve_can_submit(
        "alpaca"
    )

    assert allowed is False
    assert reason in {"kill_switch_active", "kill_switch_unreadable"}


def test_the_cli_arms_the_switch_the_resolver_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Writer and reader must land on the same file.

    The two used separate path literals, which is how the reader ended up
    watching a file `atlas kill` never wrote. Asserting through the real command
    rather than the helper is the point: a test that arms the switch itself
    would agree with the resolver no matter where the CLI writes.
    """
    from atlas_agent.cli import main
    from atlas_agent.config.paths import get_safety_dir_for
    from atlas_agent.brokers.resolver import _advanced_kill_switch_mode
    from atlas_agent.config.builder import get_effective_config

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    main(["kill", "flatten-all"])

    config = get_effective_config()
    assert (get_safety_dir_for(config) / "kill_switch.json").exists()
    assert _advanced_kill_switch_mode(config) == "flatten_all"


def test_normal_mode_on_both_switches_leaves_the_path_open(ready_to_submit) -> None:
    """The negative case, which is what makes the others mean anything.

    Without it, a resolver that refused unconditionally would pass every
    assertion above.
    """
    from atlas_agent.brokers.resolver import BrokerResolver

    _advanced_switch(ready_to_submit).set_mode("normal", reason="reset", actor="user")

    allowed, reason, _message = BrokerResolver(ready_to_submit)._resolve_can_submit(
        "alpaca"
    )

    assert (allowed, reason) == (True, "live_submit_ready")
