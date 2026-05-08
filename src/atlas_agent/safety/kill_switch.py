from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Sequence

from atlas_agent.brokers.base import Broker
from atlas_agent.execution.order import FlattenResult, OrderResult


KILL_SWITCH_MODES = ("soft", "cancel", "flatten")
MODE_RANK = {"soft": 0, "cancel": 1, "flatten": 2}
GENERIC_CANCEL_ORDER_ID = "kill-switch-cancel-all"
AuditHook = Callable[[str, str, dict[str, Any]], None]


@dataclass(frozen=True)
class KillSwitchState:
    enabled: bool
    mode: str
    reason: str
    actor: str
    updated_at: str
    activated_at: str | None = None
    deactivated_at: str | None = None

    @classmethod
    def disabled(cls) -> KillSwitchState:
        return cls(
            enabled=False,
            mode="soft",
            reason="",
            actor="system",
            updated_at="",
            activated_at=None,
            deactivated_at=None,
        )


@dataclass(frozen=True)
class KillSwitchTransition:
    changed: bool
    state: KillSwitchState
    message: str
    cancel_results: tuple[OrderResult, ...] = ()
    flatten_result: FlattenResult | None = None


class KillSwitchController:
    def __init__(
        self,
        *,
        state_path: str | Path = "memory/kill_switch_state.json",
        enabled_flag_path: str | Path = "memory/kill_switch.enabled",
        lock_path: str | Path | None = None,
        audit_hook: AuditHook | None = None,
    ) -> None:
        self.state_path = Path(state_path)
        self.enabled_flag_path = Path(enabled_flag_path)
        self.lock_path = Path(lock_path) if lock_path is not None else self.state_path.with_suffix(
            self.state_path.suffix + ".lock"
        )
        self.audit_hook = audit_hook
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.enabled_flag_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._thread_lock = threading.RLock()

    def status(self) -> KillSwitchState:
        with self._locked():
            state = self._read_state()
            self._sync_enabled_flag(state.enabled)
            return state

    def is_enabled(self) -> bool:
        return self.status().enabled

    def enable(
        self,
        *,
        mode: str = "soft",
        reason: str = "",
        actor: str = "system",
        broker: Broker | None = None,
        working_order_ids: Sequence[str] = (),
        cancel_working_orders: Callable[[], Sequence[OrderResult]] | None = None,
        flatten_strategy: str = "market",
        flatten_bps: int = 25,
    ) -> KillSwitchTransition:
        requested_mode = _normalize_mode(mode)
        if flatten_bps < 0:
            raise ValueError("flatten_bps must be non-negative")
        if flatten_strategy not in {"market", "aggressive_limit"}:
            raise ValueError(f"unsupported flatten strategy: {flatten_strategy}")
        with self._locked():
            previous = self._read_state()
            previous_rank = MODE_RANK[previous.mode] if previous.enabled else -1
            requested_rank = MODE_RANK[requested_mode]
            if previous.enabled and previous_rank >= requested_rank:
                self._sync_enabled_flag(True)
                self._emit_audit(
                    "kill_switch_noop",
                    actor=actor,
                    payload={
                        "requested_mode": requested_mode,
                        "current_mode": previous.mode,
                        "reason": reason or previous.reason,
                        "changed": False,
                    },
                )
                return KillSwitchTransition(
                    changed=False,
                    state=previous,
                    message="kill switch already enabled at equal or stronger mode",
                )

            now_iso = _utc_now_iso()
            next_state = KillSwitchState(
                enabled=True,
                mode=requested_mode,
                reason=reason or previous.reason or "manual toggle",
                actor=actor,
                updated_at=now_iso,
                activated_at=previous.activated_at or now_iso,
                deactivated_at=None,
            )
            self._write_state(next_state)
            self._sync_enabled_flag(True)

            cancel_results: tuple[OrderResult, ...] = ()
            flatten_result: FlattenResult | None = None
            messages = [f"kill switch enabled ({requested_mode})"]

            if requested_rank >= MODE_RANK["cancel"] and previous_rank < MODE_RANK["cancel"]:
                cancel_results = self._run_cancel_actions(
                    broker=broker,
                    working_order_ids=working_order_ids,
                    cancel_working_orders=cancel_working_orders,
                )
                messages.append(
                    f"cancel attempted: {len(cancel_results)}"
                )
            if requested_rank >= MODE_RANK["flatten"] and previous_rank < MODE_RANK["flatten"]:
                flatten_result = self._run_flatten(
                    broker=broker,
                    strategy=flatten_strategy,
                    bps=flatten_bps,
                )
                messages.append(flatten_result.status)
            self._emit_audit(
                "kill_switch_enabled",
                actor=actor,
                payload={
                    "mode": requested_mode,
                    "reason": next_state.reason,
                    "changed": True,
                    "cancel_attempted": len(cancel_results),
                    "flatten_status": flatten_result.status if flatten_result is not None else None,
                    "flatten_closed": flatten_result.closed if flatten_result is not None else None,
                    "flatten_failed": flatten_result.failed if flatten_result is not None else None,
                    "updated_at": next_state.updated_at,
                },
            )
            return KillSwitchTransition(
                changed=True,
                state=next_state,
                message="; ".join(messages),
                cancel_results=cancel_results,
                flatten_result=flatten_result,
            )

    def disable(
        self,
        *,
        reason: str = "",
        actor: str = "system",
    ) -> KillSwitchTransition:
        with self._locked():
            previous = self._read_state()
            if not previous.enabled:
                self._sync_enabled_flag(False)
                self._emit_audit(
                    "kill_switch_noop",
                    actor=actor,
                    payload={
                        "requested_state": "disabled",
                        "current_state": "disabled",
                        "reason": reason or previous.reason,
                        "changed": False,
                    },
                )
                return KillSwitchTransition(
                    changed=False,
                    state=previous,
                    message="kill switch already disabled",
                )
            now_iso = _utc_now_iso()
            next_state = KillSwitchState(
                enabled=False,
                mode=previous.mode,
                reason=reason or previous.reason,
                actor=actor,
                updated_at=now_iso,
                activated_at=previous.activated_at,
                deactivated_at=now_iso,
            )
            self._write_state(next_state)
            self._sync_enabled_flag(False)
            self._emit_audit(
                "kill_switch_disabled",
                actor=actor,
                payload={
                    "mode": previous.mode,
                    "reason": next_state.reason,
                    "changed": True,
                    "updated_at": next_state.updated_at,
                },
            )
            return KillSwitchTransition(
                changed=True,
                state=next_state,
                message="kill switch disabled",
            )

    def _run_cancel_actions(
        self,
        *,
        broker: Broker | None,
        working_order_ids: Sequence[str],
        cancel_working_orders: Callable[[], Sequence[OrderResult]] | None,
    ) -> tuple[OrderResult, ...]:
        if cancel_working_orders is not None:
            return tuple(cancel_working_orders())
        if broker is None or not working_order_ids:
            return ()
        seen: set[str] = set()
        results: list[OrderResult] = []
        for order_id in working_order_ids:
            clean = order_id.strip()
            if not clean or clean in seen:
                continue
            seen.add(clean)
            results.append(broker.cancel_order(clean))
        return tuple(results)

    def _run_flatten(
        self,
        *,
        broker: Broker | None,
        strategy: str,
        bps: int,
    ) -> FlattenResult:
        if broker is None:
            return FlattenResult(
                accepted=False,
                status="failed",
                message="flatten requested but broker is unavailable",
                strategy=strategy,
                bps=bps,
                attempted=0,
                closed=0,
                failed=0,
            )
        try:
            return broker.flatten_all(strategy=strategy, bps=bps)
        except Exception as exc:
            return FlattenResult(
                accepted=False,
                status="failed",
                message=f"flatten call failed: {exc}",
                strategy=strategy,
                bps=bps,
                attempted=0,
                closed=0,
                failed=0,
            )

    @contextmanager
    def _locked(self):
        with self._thread_lock:
            with self.lock_path.open("a+", encoding="utf-8") as lock_file:
                _lock_file(lock_file)
                try:
                    yield
                finally:
                    _unlock_file(lock_file)

    def _read_state(self) -> KillSwitchState:
        if not self.state_path.exists():
            if self.enabled_flag_path.exists():
                return KillSwitchState(
                    enabled=True,
                    mode="soft",
                    reason="legacy enabled flag detected",
                    actor="legacy",
                    updated_at=_utc_now_iso(),
                    activated_at=_utc_now_iso(),
                    deactivated_at=None,
                )
            return KillSwitchState.disabled()
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, ValueError):
            if self.enabled_flag_path.exists():
                return KillSwitchState(
                    enabled=True,
                    mode="soft",
                    reason="state file unreadable; legacy enabled flag used",
                    actor="system",
                    updated_at=_utc_now_iso(),
                    activated_at=_utc_now_iso(),
                    deactivated_at=None,
                )
            return KillSwitchState.disabled()
        mode = _normalize_mode(str(raw.get("mode", "soft")))
        return KillSwitchState(
            enabled=bool(raw.get("enabled", False)),
            mode=mode,
            reason=str(raw.get("reason", "")),
            actor=str(raw.get("actor", "system")),
            updated_at=str(raw.get("updated_at", "")),
            activated_at=(
                str(raw.get("activated_at")) if raw.get("activated_at") is not None else None
            ),
            deactivated_at=(
                str(raw.get("deactivated_at")) if raw.get("deactivated_at") is not None else None
            ),
        )

    def _write_state(self, state: KillSwitchState) -> None:
        payload = {
            "enabled": state.enabled,
            "mode": state.mode,
            "reason": state.reason,
            "actor": state.actor,
            "updated_at": state.updated_at,
            "activated_at": state.activated_at,
            "deactivated_at": state.deactivated_at,
        }
        tmp_path = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(self.state_path)

    def _sync_enabled_flag(self, enabled: bool) -> None:
        if enabled:
            self.enabled_flag_path.write_text("enabled\n", encoding="utf-8")
            return
        if self.enabled_flag_path.exists():
            self.enabled_flag_path.unlink()

    def _emit_audit(
        self,
        event_type: str,
        *,
        actor: str,
        payload: dict[str, Any],
    ) -> None:
        if self.audit_hook is None:
            return
        try:
            self.audit_hook(event_type, actor, payload)
        except Exception:
            return


def _normalize_mode(mode: str) -> str:
    normalized = mode.strip().lower()
    if normalized not in KILL_SWITCH_MODES:
        raise ValueError(f"kill switch mode must be one of: {', '.join(KILL_SWITCH_MODES)}")
    return normalized


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _lock_file(handle) -> None:
    try:
        import fcntl  # type: ignore

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    except ImportError:
        return


def _unlock_file(handle) -> None:
    try:
        import fcntl  # type: ignore

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except ImportError:
        return
