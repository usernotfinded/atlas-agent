from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import json
from pathlib import Path

from atlas_agent.execution.order import AccountSnapshot, FlattenResult, Order, OrderResult
from atlas_agent.portfolio.positions import Position
from atlas_agent.safety.deadman import DeadmanConfig, DeadmanSwitch, write_deadman_heartbeat
from atlas_agent.safety.kill_switch import KillSwitchController


@dataclass
class FixedStateDetector:
    state: str = "open"

    def get_state(self, now=None) -> str:
        return self.state


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.current = start

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: int) -> None:
        self.current = self.current + timedelta(seconds=seconds)


@dataclass
class FlattenProbeBroker:
    flatten_calls: int = 0
    last_strategy: str | None = None
    last_bps: int | None = None

    def get_account(self) -> AccountSnapshot:
        return AccountSnapshot(cash=0.0, equity=0.0, buying_power=0.0, mode="paper")

    def get_positions(self) -> list[Position]:
        return []

    def place_order(self, order: Order) -> OrderResult:
        return OrderResult(True, True, order.id, "filled", "filled")

    def cancel_order(self, order_id: str) -> OrderResult:
        return OrderResult(True, False, order_id, "cancelled", "cancelled")

    def flatten_all(self, strategy: str = "market", bps: int = 25) -> FlattenResult:
        self.flatten_calls += 1
        self.last_strategy = strategy
        self.last_bps = bps
        return FlattenResult(
            accepted=True,
            status="flattened",
            message="flatten ok",
            strategy=strategy,
            bps=bps,
            attempted=1,
            closed=1,
            failed=0,
        )


def make_deadman(
    tmp_path,
    *,
    detector_state: str = "open",
    timeout_minutes: int = 1,
    action: str = "soft",
    auto_reset: bool = True,
    active_outside_market: bool = False,
    flatten_strategy: str = "market",
    flatten_bps: int = 25,
):
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    controller = KillSwitchController(
        state_path=tmp_path / "kill-switch-state.json",
        enabled_flag_path=tmp_path / "kill-switch.enabled",
        lock_path=tmp_path / "kill-switch.lock",
    )
    notifications: list[str] = []
    deadman = DeadmanSwitch(
        kill_switch=controller,
        config=DeadmanConfig(
            timeout_minutes=timeout_minutes,
            action=action,
            auto_reset=auto_reset,
            active_outside_market=active_outside_market,
            check_interval_seconds=0.01,
            flatten_strategy=flatten_strategy,
            flatten_bps=flatten_bps,
        ),
        market_detector=FixedStateDetector(detector_state),
        notifiers=[notifications.append],
        now_func=clock.now,
    )
    return deadman, controller, clock, notifications


def test_deadman_triggers_soft_mode_after_timeout(tmp_path) -> None:
    deadman, controller, clock, notifications = make_deadman(tmp_path)

    asyncio.run(deadman.tick())
    assert controller.status().enabled is False

    clock.advance(61)
    triggered = asyncio.run(deadman.tick())
    assert triggered is True
    state = controller.status()
    assert state.enabled is True
    assert state.mode == "soft"
    assert len(notifications) == 1

    # idempotent while still in triggered state
    clock.advance(61)
    triggered_again = asyncio.run(deadman.tick())
    assert triggered_again is False
    assert len(notifications) == 1


def test_deadman_ignores_timeout_outside_market_by_default(tmp_path) -> None:
    deadman, controller, clock, notifications = make_deadman(
        tmp_path,
        detector_state="closed",
        active_outside_market=False,
    )
    clock.advance(120)

    triggered = asyncio.run(deadman.tick())
    assert triggered is False
    assert controller.status().enabled is False
    assert notifications == []


def test_deadman_can_run_outside_market_when_enabled(tmp_path) -> None:
    deadman, controller, clock, _ = make_deadman(
        tmp_path,
        detector_state="closed",
        active_outside_market=True,
        action="cancel",
    )
    clock.advance(120)

    triggered = asyncio.run(deadman.tick())
    assert triggered is True
    state = controller.status()
    assert state.enabled is True
    assert state.mode == "cancel"


def test_deadman_heartbeat_resets_timeout(tmp_path) -> None:
    deadman, controller, clock, _ = make_deadman(tmp_path, timeout_minutes=1)

    clock.advance(50)
    deadman.record_heartbeat(source="cli", actor="user:1")
    clock.advance(20)
    assert asyncio.run(deadman.tick()) is False
    assert controller.status().enabled is False

    clock.advance(45)
    assert asyncio.run(deadman.tick()) is True
    assert controller.status().enabled is True


def test_deadman_auto_reset_interaction_toggle(tmp_path) -> None:
    deadman_true, controller_true, clock_true, _ = make_deadman(
        tmp_path / "on",
        auto_reset=True,
    )
    clock_true.advance(50)
    assert deadman_true.record_interaction(source="telegram", actor="user:1") is True
    clock_true.advance(20)
    assert asyncio.run(deadman_true.tick()) is False
    clock_true.advance(50)
    assert asyncio.run(deadman_true.tick()) is True
    assert controller_true.status().enabled is True

    deadman_false, controller_false, clock_false, _ = make_deadman(
        tmp_path / "off",
        auto_reset=False,
    )
    clock_false.advance(50)
    assert deadman_false.record_interaction(source="telegram", actor="user:1") is False
    clock_false.advance(20)
    assert asyncio.run(deadman_false.tick()) is True
    assert controller_false.status().enabled is True


def test_deadman_reads_external_heartbeat_file(tmp_path) -> None:
    import asyncio

    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    controller = KillSwitchController(
        state_path=tmp_path / "kill-switch-state.json",
        enabled_flag_path=tmp_path / "kill-switch.enabled",
        lock_path=tmp_path / "kill-switch.lock",
    )
    heartbeat_path = tmp_path / "memory" / "deadman_heartbeat.json"
    deadman = DeadmanSwitch(
        kill_switch=controller,
        config=DeadmanConfig(timeout_minutes=1, action="soft", check_interval_seconds=0.01),
        market_detector=FixedStateDetector("open"),
        now_func=clock.now,
        heartbeat_path=heartbeat_path,
    )

    clock.advance(50)
    write_deadman_heartbeat(
        heartbeat_path,
        source="external-cli",
        actor="user:22",
        now=clock.now(),
    )
    clock.advance(20)
    assert asyncio.run(deadman.tick()) is False
    assert controller.status().enabled is False

    clock.advance(45)
    assert asyncio.run(deadman.tick()) is True
    assert controller.status().enabled is True


def test_deadman_notifier_fanout_and_trigger_hook(tmp_path) -> None:
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    controller = KillSwitchController(
        state_path=tmp_path / "kill-switch-state.json",
        enabled_flag_path=tmp_path / "kill-switch.enabled",
        lock_path=tmp_path / "kill-switch.lock",
    )
    sent: list[str] = []
    trigger_events: list[dict[str, object]] = []

    def bad_notifier(_: str) -> None:
        raise RuntimeError("gateway offline")

    def good_notifier(msg: str) -> None:
        sent.append(msg)

    deadman = DeadmanSwitch(
        kill_switch=controller,
        config=DeadmanConfig(timeout_minutes=1, action="soft", check_interval_seconds=0.01),
        market_detector=FixedStateDetector("open"),
        notifiers=[bad_notifier, good_notifier],
        trigger_hook=lambda payload: trigger_events.append(payload),
        now_func=clock.now,
    )

    clock.advance(61)
    assert asyncio.run(deadman.tick()) is True
    assert len(sent) == 1
    assert "Dead man's switch activated" in sent[0]
    assert len(trigger_events) == 1
    assert trigger_events[0]["mode"] == "soft"


def test_deadman_external_heartbeat_emits_audit_hook(tmp_path) -> None:
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    controller = KillSwitchController(
        state_path=tmp_path / "kill-switch-state.json",
        enabled_flag_path=tmp_path / "kill-switch.enabled",
        lock_path=tmp_path / "kill-switch.lock",
    )
    heartbeat_path = tmp_path / "memory" / "deadman_heartbeat.json"
    audit_events: list[tuple[str, str, dict[str, object]]] = []

    def audit_hook(event_type: str, actor: str, payload: dict[str, object]) -> None:
        audit_events.append((event_type, actor, payload))

    deadman = DeadmanSwitch(
        kill_switch=controller,
        config=DeadmanConfig(timeout_minutes=5, action="soft", check_interval_seconds=0.01),
        market_detector=FixedStateDetector("open"),
        now_func=clock.now,
        heartbeat_path=heartbeat_path,
        audit_hook=audit_hook,
    )

    clock.advance(10)
    write_deadman_heartbeat(
        heartbeat_path,
        source="external",
        actor="user:55",
        now=clock.now(),
    )
    _ = deadman.status()

    assert any(event[0] == "deadman_heartbeat_external" for event in audit_events)


def test_deadman_flatten_propagates_strategy_and_bps_to_broker(tmp_path) -> None:
    deadman, controller, clock, _ = make_deadman(
        tmp_path,
        action="flatten",
        flatten_strategy="aggressive_limit",
        flatten_bps=42,
    )
    broker = FlattenProbeBroker()

    clock.advance(61)
    assert asyncio.run(deadman.tick(broker=broker)) is True

    state = controller.status()
    assert state.enabled is True
    assert state.mode == "flatten"
    assert broker.flatten_calls == 1
    assert broker.last_strategy == "aggressive_limit"
    assert broker.last_bps == 42


def test_deadman_heartbeat_write_is_atomic(tmp_path: Path) -> None:
    target = tmp_path / "deadman_heartbeat.json"
    write_deadman_heartbeat(target, source="test", actor="user:1")
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["source"] == "test"
    assert payload["actor"] == "user:1"
    assert not (tmp_path / "deadman_heartbeat.json.tmp").exists()
