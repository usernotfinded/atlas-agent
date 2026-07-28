# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/brokers/test_live_submit_gate_chain.py
# PURPOSE: Asserts the live-submit invariant over every combination of its
#         gates, rather than one case per gate.
# DEPS:    itertools, json, pathlib, datetime, pytest, atlas_agent.
# ==============================================================================

"""Exhaustive coverage for `BrokerResolver._resolve_can_submit`.

The governance document states that `can_submit` is false unless every opt-in
gate is satisfied. That is one property, not eight cases, so it is tested as
one property: for each of the 2^8 ways of breaking a subset of the gates,
`can_submit` must be true exactly when the broken subset is empty.

Writing a case per gate would assert less for more code. It only ever probes
one gate at a time, so it cannot see an interaction — a gate that silently
stops denying whenever some other gate is also broken passes a per-gate suite
and fails here. The enumeration is small enough to run in full, so there is no
reason to sample it.

Reaching `live_submit_ready` at all is the other half of the claim, and the
empty subset covers it: without that, a chain wired to deny unconditionally
would look perfectly correct.
"""

# --- IMPORTS ---

from __future__ import annotations

import itertools
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

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


def _build_live_ready_config(tmp_path: Path, monkeypatch) -> AtlasConfig:
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


# Each entry breaks exactly one gate, and names the code the resolver reports
# when that gate is the first one it reaches.
GateBreaker = Callable[[AtlasConfig, pytest.MonkeyPatch], None]


def _break_broker_capability(config: AtlasConfig, _monkeypatch) -> None:
    """Point at a broker the support registry marks as not live-submit capable."""
    config.broker.provider = "ccxt"


def _break_live_submit_flag(config: AtlasConfig, _monkeypatch) -> None:
    config.broker.enable_live_submit = False


def _break_live_trading_flag(config: AtlasConfig, _monkeypatch) -> None:
    config.broker.enable_live_trading = False


def _break_kill_switch(config: AtlasConfig, _monkeypatch) -> None:
    state_path = Path(config.memory_dir) / "kill_switch_state.json"
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


def _break_trading_mode(config: AtlasConfig, _monkeypatch) -> None:
    config.trading_mode = "paper"


def _break_approval_mode(config: AtlasConfig, _monkeypatch) -> None:
    config.safety.order_approval_mode = "disabled_live"


def _break_leverage(config: AtlasConfig, _monkeypatch) -> None:
    config.risk.allow_leverage = True


def _break_credentials(_config: AtlasConfig, monkeypatch) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)


def _break_opt_in(config: AtlasConfig, _monkeypatch) -> None:
    (Path(config.audit_dir) / "live_submit_opt_in.jsonl").unlink()


#: Ordered as the resolver evaluates them, so the expected code for a broken
#: subset is the code of its earliest member.
GATES: list[tuple[str, GateBreaker, str]] = [
    ("broker_capability", _break_broker_capability, "broker_not_live_submit_capable"),
    ("live_submit_flag", _break_live_submit_flag, "live_submit_disabled"),
    ("live_trading_flag", _break_live_trading_flag, "live_trading_disabled"),
    ("kill_switch", _break_kill_switch, "kill_switch_active"),
    ("trading_mode", _break_trading_mode, "trading_mode_not_live"),
    ("approval_mode", _break_approval_mode, "approval_disabled"),
    ("leverage", _break_leverage, "leverage_enabled"),
    ("credentials", _break_credentials, "credentials_missing"),
    ("opt_in_record", _break_opt_in, "opt_in_file_missing"),
]


def _can_submit(config: AtlasConfig) -> tuple[bool, str]:
    resolver = BrokerResolver(config)
    allowed, code, _message = resolver._resolve_can_submit(config.broker.provider)
    return allowed, code


def _all_gate_subsets() -> list[tuple[int, ...]]:
    indices = range(len(GATES))
    return [
        subset
        for size in indices
        for subset in itertools.combinations(indices, size)
    ] + [tuple(indices)]


@pytest.mark.parametrize("broken", _all_gate_subsets(), ids=lambda s: "-".join(
    GATES[i][0] for i in s) or "none_broken")
def test_can_submit_is_true_exactly_when_no_gate_is_broken(
    broken: tuple[int, ...], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _build_live_ready_config(tmp_path, monkeypatch)
    for index in broken:
        GATES[index][1](config, monkeypatch)

    allowed, code = _can_submit(config)

    assert allowed is (len(broken) == 0)
    if broken:
        # The resolver reports the first gate it reaches, so the code must belong
        # to the earliest broken one. Asserting the specific code — not merely
        # "some failure" — is what stops one gate's denial from standing in for
        # another's.
        assert code == GATES[min(broken)][2]
    else:
        assert code == "live_submit_ready"


def test_unreadable_kill_switch_state_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A state file that cannot be read must deny, never read as normal."""
    config = _build_live_ready_config(tmp_path, monkeypatch)
    state_path = Path(config.memory_dir) / "kill_switch_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("{ not json", encoding="utf-8")

    allowed, code = _can_submit(config)

    assert allowed is False
    assert code in {"kill_switch_active", "kill_switch_unreadable"}


def test_opt_in_does_not_survive_a_change_to_its_risk_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An opt-in is granted against a fingerprint of the limits it was given under."""
    config = _build_live_ready_config(tmp_path, monkeypatch)
    config.risk.max_order_notional = 999999.0

    allowed, code = _can_submit(config)

    assert allowed is False
    assert code != "live_submit_ready"


# ==============================================================================
# DIFFERENTIAL: THE GUARDS AGAINST THE RESOLVER
# ==============================================================================

# The live-submit rule is written twice. `BrokerResolver` reports it as a status
# with a reason code per gate; `brokers/guards.py` raises a single exception. The
# resolver reuses the guard for the broker-capability half, but re-implements the
# operator flags, because folding them together would make a forgotten flag read
# as an unsupported broker.
#
# Two implementations of a safety rule drift, and these two already did once: the
# resolver answered `live_submit_ready` for brokers the inventory marks disabled,
# for as long as the guard that disagreed had no caller. These tests pin the
# agreement instead of trusting it.

#: Indices into GATES that `guard_submit` also checks. It is a subset — the
#: resolver additionally gates on the kill switch, approval mode, leverage,
#: credentials, and the opt-in record.
GUARD_SUBMIT_GATE_INDICES = frozenset({0, 1, 2, 4})

#: The reason codes the resolver reports for exactly those gates.
GUARD_SUBMIT_CODES = frozenset(GATES[i][2] for i in GUARD_SUBMIT_GATE_INDICES)


def _guard_submit_refuses(config: AtlasConfig) -> bool:
    from atlas_agent.brokers.base import BrokerConfigurationError
    from atlas_agent.brokers.guards import guard_submit

    try:
        guard_submit(broker_id=config.broker.provider, config=config)
    except BrokerConfigurationError:
        return True
    return False


@pytest.mark.parametrize("broken", _all_gate_subsets(), ids=lambda s: "-".join(
    GATES[i][0] for i in s) or "none_broken")
def test_guard_submit_never_disagrees_with_the_resolver(
    broken: tuple[int, ...], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _build_live_ready_config(tmp_path, monkeypatch)
    for index in broken:
        GATES[index][1](config, monkeypatch)

    refused = _guard_submit_refuses(config)
    allowed, code = _can_submit(config)

    assert refused is bool(GUARD_SUBMIT_GATE_INDICES & set(broken))

    if refused:
        # The resolver must deny too. Its reason may belong to a gate the guard
        # does not check — the kill switch is reached before trading_mode — so the
        # denial is what has to match, not the wording.
        assert allowed is False, (
            "guard_submit refused a configuration the resolver reported as ready"
        )
    else:
        # Nothing the guard checks is broken, so the resolver must not be denying
        # for one of the guard's own reasons.
        assert code not in GUARD_SUBMIT_CODES, (
            f"the resolver denied with {code}, a gate guard_submit shares, while "
            "guard_submit allowed the same configuration"
        )


@pytest.mark.parametrize(
    "broker_id", ["alpaca", "paper", "binance", "ccxt", "ibkr", "ibkr_stub", "unknown"]
)
def test_guard_sync_admits_no_broker_the_resolver_refuses(
    broker_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A guard may be stricter than the live path. It may never be looser.

    `guard_sync` admitted `paper`, which is in the inventory with
    `read_only_supported=True`, while the resolver refuses it as
    `live_broker_unsupported`. Read-only or not, a guard that answers yes where
    the live path answers no is a guard that would loosen the live path the day
    someone wires it in — which is precisely what its docstring offers to do.
    """
    from atlas_agent.brokers.base import BrokerConfigurationError
    from atlas_agent.brokers.guards import guard_sync

    config = _build_live_ready_config(tmp_path, monkeypatch)
    # `live_broker` is a read-only view of `broker.provider`, which is what the
    # resolver reads in live mode.
    config.broker.provider = broker_id

    try:
        guard_sync(broker_id=broker_id, config=config)
        guard_allows = True
    except BrokerConfigurationError:
        guard_allows = False

    resolver_allows = BrokerResolver(config).resolve_status("live").can_sync

    if guard_allows:
        assert resolver_allows, (
            f"guard_sync admits {broker_id!r} for live sync while BrokerResolver "
            "refuses it"
        )
