from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from atlas_agent.execution.order import AccountSnapshot, FlattenResult, Order, OrderResult
from atlas_agent.portfolio.positions import Position
from atlas_agent.safety.kill_switch import KillSwitchController


@dataclass
class StubBroker:
    cancel_calls: list[str] = field(default_factory=list)
    flatten_calls: int = 0
    flatten_result: FlattenResult = field(
        default_factory=lambda: FlattenResult(
            accepted=True,
            status="flattened",
            message="ok",
            strategy="market",
            bps=25,
            attempted=0,
            closed=0,
            failed=0,
        )
    )

    def get_account(self) -> AccountSnapshot:
        return AccountSnapshot(cash=0.0, equity=0.0, buying_power=0.0, mode="paper")

    def get_positions(self) -> list[Position]:
        return []

    def place_order(self, order: Order) -> OrderResult:
        return OrderResult(True, True, order.id, "filled", "filled")

    def cancel_order(self, order_id: str) -> OrderResult:
        self.cancel_calls.append(order_id)
        return OrderResult(
            accepted=True,
            filled=False,
            order_id=order_id,
            status="cancelled",
            message="cancelled",
        )

    def flatten_all(self, strategy: str = "market", bps: int = 25) -> FlattenResult:
        self.flatten_calls += 1
        return self.flatten_result


def make_controller(tmp_path) -> KillSwitchController:
    return KillSwitchController(
        state_path=tmp_path / "kill-switch-state.json",
        enabled_flag_path=tmp_path / "kill-switch.enabled",
        lock_path=tmp_path / "kill-switch.lock",
    )


def test_kill_switch_mode_transitions_are_idempotent(tmp_path) -> None:
    controller = make_controller(tmp_path)
    broker = StubBroker(
        flatten_result=FlattenResult(
            accepted=True,
            status="flattened",
            message="closed all",
            strategy="market",
            bps=25,
            attempted=2,
            closed=2,
            failed=0,
        )
    )

    soft = controller.enable(mode="soft", reason="manual", actor="user:1")
    assert soft.changed is True
    assert soft.state.enabled is True
    assert soft.state.mode == "soft"

    soft_again = controller.enable(mode="soft", reason="duplicate", actor="user:1")
    assert soft_again.changed is False

    cancel = controller.enable(
        mode="cancel",
        actor="user:1",
        broker=broker,
        working_order_ids=("ord-1", "ord-2", "ord-2"),
    )
    assert cancel.changed is True
    assert cancel.state.mode == "cancel"
    assert len(cancel.cancel_results) == 2
    assert broker.cancel_calls == ["ord-1", "ord-2"]

    flatten = controller.enable(mode="flatten", actor="user:1", broker=broker)
    assert flatten.changed is True
    assert flatten.state.mode == "flatten"
    assert flatten.flatten_result is not None
    assert flatten.flatten_result.status == "flattened"
    assert broker.flatten_calls == 1

    flatten_again = controller.enable(mode="flatten", actor="user:1", broker=broker)
    assert flatten_again.changed is False
    assert broker.flatten_calls == 1


def test_kill_switch_flatten_without_broker_returns_failure_report(tmp_path) -> None:
    controller = make_controller(tmp_path)

    result = controller.enable(mode="flatten", actor="user:99")

    assert result.changed is True
    assert result.state.enabled is True
    assert result.state.mode == "flatten"
    assert result.flatten_result is not None
    assert result.flatten_result.accepted is False
    assert result.flatten_result.status == "failed"


def test_kill_switch_state_persists_across_instances(tmp_path) -> None:
    controller_a = make_controller(tmp_path)
    controller_a.enable(mode="cancel", reason="ops", actor="cron")

    controller_b = make_controller(tmp_path)
    state = controller_b.status()
    assert state.enabled is True
    assert state.mode == "cancel"
    assert state.reason == "ops"
    assert state.actor == "cron"

    disabled = controller_b.disable(reason="clear", actor="user:1")
    assert disabled.changed is True
    assert disabled.state.enabled is False


def test_kill_switch_flatten_partial_success_is_reported(tmp_path) -> None:
    controller = make_controller(tmp_path)
    broker = StubBroker(
        flatten_result=FlattenResult(
            accepted=True,
            status="partial",
            message="1 symbol failed",
            strategy="aggressive_limit",
            bps=30,
            attempted=2,
            closed=1,
            failed=1,
            failed_symbols=("ETH-USD",),
        )
    )

    result = controller.enable(
        mode="flatten",
        actor="user:2",
        broker=broker,
        flatten_strategy="aggressive_limit",
        flatten_bps=30,
    )

    assert result.flatten_result is not None
    assert result.flatten_result.status == "partial"
    assert result.flatten_result.failed_symbols == ("ETH-USD",)


def test_kill_switch_emits_audit_events_on_transitions(tmp_path) -> None:
    events: list[tuple[str, str, dict[str, object]]] = []

    def audit_hook(event_type: str, actor: str, payload: dict[str, object]) -> None:
        events.append((event_type, actor, payload))

    controller = KillSwitchController(
        state_path=tmp_path / "kill-switch-state.json",
        enabled_flag_path=tmp_path / "kill-switch.enabled",
        lock_path=tmp_path / "kill-switch.lock",
        audit_hook=audit_hook,
    )

    controller.enable(mode="soft", reason="drill", actor="user:1")
    controller.enable(mode="soft", reason="duplicate", actor="user:1")
    controller.disable(reason="done", actor="user:1")

    event_types = [item[0] for item in events]
    assert "kill_switch_enabled" in event_types
    assert "kill_switch_noop" in event_types
    assert "kill_switch_disabled" in event_types


def test_kill_switch_no_fixed_tmp_after_write(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    controller.enable(mode="soft", reason="test", actor="user:1")
    assert (tmp_path / "kill-switch-state.json").exists()
    assert not (tmp_path / "kill-switch-state.json.tmp").exists()
