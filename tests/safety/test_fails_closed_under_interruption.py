# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/safety/test_fails_closed_under_interruption.py
# PURPOSE: One place that answers "what happens when this breaks mid-flight?" for
#         every interruption the system can meet.
# DEPS:    json, pathlib, tempfile, pytest, atlas_agent.
# ==============================================================================

"""Evidence for the operational audit gate.

`docs/bounded-live-autonomy-governance.md` requires, before any L4-like path, an
operational audit that validates "monitoring, incident response, failover
behavior, and proof that the system fails closed under error or interruption".

The proof existed in pieces. The kill switch's state reader documents its own
fail-closed doctrine, the resolver answers `kill_switch_unreadable`, the submit
path refuses a corrupt pending order, and the deadman blocks a hung cycle — each
asserted in its own module, next to the code it covers. What no one could point
at was the *set*: a reviewer asking "what happens when this breaks mid-flight?"
had to know which files to open and trust that the list was complete.

This is that list. Each case names a way the system can be interrupted and
asserts it refuses rather than proceeds. It deliberately overlaps other tests —
the value here is the enumeration, not the individual assertion, and a fail-closed
property that is only checked beside its own implementation is one refactor away
from being checked nowhere.

A case that starts failing is not a test to fix. It is a mode in which this
system would keep going after something broke.
"""

# --- IMPORTS ---

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

pytestmark = pytest.mark.quick


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _workspace(tmp_path: Path):
    from atlas_agent.config import AtlasConfig

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
    return config


def test_an_unreadable_kill_switch_arms_rather_than_disarms(tmp_path: Path) -> None:
    """Someone wrote that file. Not being able to read it is not permission."""
    from atlas_agent.safety.kill_switch import KillSwitchController

    controller = KillSwitchController(
        state_path=tmp_path / "kill_switch_state.json",
        enabled_flag_path=tmp_path / "kill_switch.enabled",
    )
    (tmp_path / "kill_switch_state.json").write_text("{ not json", encoding="utf-8")

    assert controller.is_enabled() is True


def test_an_unreadable_kill_switch_stops_live_submit(tmp_path: Path) -> None:
    """The same interruption, seen from the order path."""
    from atlas_agent.brokers.resolver import BrokerResolver

    config = _workspace(tmp_path)
    config.broker.provider = "alpaca"
    # The gates ahead of the kill switch are satisfied on purpose. Without that,
    # the chain refuses at `live_submit_disabled` and this case would pass while
    # proving nothing about an unreadable kill switch.
    config.broker.enable_live_submit = True
    config.broker.enable_live_trading = True
    (Path(config.memory_dir) / "kill_switch_state.json").write_text(
        "{ not json", encoding="utf-8"
    )

    allowed, reason, _message = BrokerResolver(config)._resolve_can_submit("alpaca")

    assert allowed is False
    assert reason in {"kill_switch_active", "kill_switch_unreadable"}


def test_a_hung_cycle_is_blocked_by_the_deadman(tmp_path: Path) -> None:
    """Interruption by the agent simply stopping, which nothing else detects."""
    from atlas_agent.safety.kill_switch import AdvancedKillSwitch

    kill_switch = AdvancedKillSwitch(
        state_path=tmp_path / "kill_switch.json",
        heartbeat_path=tmp_path / "heartbeat.json",
    )
    kill_switch.heartbeat_manager.record(source="test")

    beat = tmp_path / "heartbeat.json"
    payload = json.loads(beat.read_text(encoding="utf-8"))
    key = "timestamp" if "timestamp" in payload else next(iter(payload))
    payload[key] = (datetime.now(UTC) - timedelta(hours=6)).isoformat()
    beat.write_text(json.dumps(payload), encoding="utf-8")

    assert kill_switch.evaluate().allowed is False


def test_a_corrupt_pending_order_is_refused_and_recorded(tmp_path: Path) -> None:
    """Interruption mid-write of the file the submit path trusts."""
    from atlas_agent.audit import AuditWriter
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order
    from atlas_agent.execution.submit_execution import run_submit_execution

    config = _workspace(tmp_path)
    manager = ApprovalManager(config.pending_orders_dir)
    path = manager.create_pending_order(
        Order(symbol="AAPL", side="buy", quantity=1, order_type="market")
    )
    path.write_text("{ truncated mid-write", encoding="utf-8")

    log = Path(config.audit_dir) / "audit.log"
    report = run_submit_execution(
        order_id=path.stem,
        config=config,
        approval_manager=manager,
        audit_writer=AuditWriter(log),
    )

    assert report.ok is False
    assert report.blocked_reason == "invalid_pending_order"
    # Failing closed silently is only half of it; the refusal has to be on record.
    assert log.exists() and log.read_text(encoding="utf-8").strip()


def test_a_non_finite_portfolio_is_refused(tmp_path: Path) -> None:
    """Interruption as bad state rather than a bad file.

    A NaN equity once disabled both percentage exposure limits, because every
    comparison against NaN is false — an order inside the absolute caps passed
    with no violations at all.
    """
    from atlas_agent.risk.manager import RiskManager
    from atlas_agent.risk.models import OrderRiskInput, PortfolioSnapshot

    order = OrderRiskInput(
        symbol="AAPL", side="buy", quantity=1, price=100.0,
        notional=100.0, leverage=1.0, confidence=0.9, stop_loss=90.0,
    )
    broken = PortfolioSnapshot(
        equity=float("nan"), cash=float("nan"), total_exposure=0.0
    )

    decision = RiskManager().evaluate_order(order, broken)

    assert decision.allowed is False
    assert "invalid_portfolio_state" in [v.rule for v in decision.violations or []]


def test_an_unloadable_config_stops_the_cli(tmp_path: Path, monkeypatch) -> None:
    """Interruption as a config the schema cannot read.

    The command has to refuse with a non-zero status, not print a note and
    return success — automation reads the exit code.
    """
    from atlas_agent.cli import main

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    toml_path = tmp_path / ".atlas" / "config.toml"
    toml_path.write_text(
        (toml_path.read_text(encoding="utf-8") if toml_path.exists() else "")
        + '\n[risk]\nmax_order_notional = "broken"\n',
        encoding="utf-8",
    )

    assert main(["status"]) != 0
