# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    safety/kill_switch.py
# PURPOSE: The master brake. Every order path consults evaluate() before acting,
#          and no order may proceed without an `allowed=True` verdict from here.
# DEPS:    safety.state (persisted mode), safety.heartbeat (liveness),
#          brokers.base (flatten/cancel), audit (every transition is recorded)
#
# DESIGN:  Two inputs decide the verdict — the operator-set mode on disk, and the
#          liveness heartbeat. Either one alone can block. Anything unexpected in
#          either resolves to the most restrictive answer available.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Sequence, Optional

from atlas_agent.brokers.base import Broker
from atlas_agent.execution.order import FlattenResult, OrderResult
from atlas_agent.safety.atomic_write import atomic_write_json
from atlas_agent.safety.models import KillSwitchMode, KillSwitchDecision
from atlas_agent.safety.state import KillSwitchState as AdvancedKillSwitchState
from atlas_agent.safety.heartbeat import HeartbeatManager
from atlas_agent.audit import AuditWriter


# ==============================================================================
# ADVANCED KILL SWITCH (mode + heartbeat)
# ==============================================================================

class AdvancedKillSwitch:

    # --- Construction ---

    def __init__(
        self,
        state_path: str | Path,
        heartbeat_path: str | Path,
        audit_writer: Optional[AuditWriter] = None,
        run_id: str = "unknown",
        iteration: Optional[int] = None,
    ):
        self.state_manager = AdvancedKillSwitchState(state_path)
        self.heartbeat_manager = HeartbeatManager(heartbeat_path)
        self.audit_writer = audit_writer
        self.run_id = run_id
        self.iteration = iteration

    # --- Decision (the function every order path calls) ---

    def evaluate(self) -> KillSwitchDecision:
        status = self.state_manager.load()
        mode = status.mode

        # Heartbeat is checked BEFORE the mode ladder, so a dead agent is blocked even
        # while the switch still reads "normal" — the mode file says what the operator
        # last asked for, not whether the system is still healthy enough to honour it.
        #
        # Skipped when already locked_down: that mode blocks everything anyway, and
        # emitting a heartbeat_expired event on every evaluate() would flood the audit
        # log of a system that is, by definition, going nowhere.
        if mode != "locked_down" and self.heartbeat_manager.is_expired():
            last_heartbeat = self.heartbeat_manager.last_heartbeat()
            last_heartbeat_iso = (
                last_heartbeat.isoformat()
                if last_heartbeat is not None
                else None
            )
            if self.audit_writer:
                self.audit_writer.write_event(
                    "heartbeat_expired",
                    run_id=self.run_id,
                    iteration=self.iteration,
                    payload={"last_heartbeat": last_heartbeat_iso},
                )
            return KillSwitchDecision(
                allowed=False,
                status="blocked",
                reason="Dead-man heartbeat expired. Execution blocked for safety.",
                mode=mode,
                diagnostics={"heartbeat_expired": True}
            )

        # The mode ladder, in increasing severity. `normal` is the ONLY branch in this
        # entire method that returns allowed=True — including the fallthrough below.
        if mode == "normal":
            return KillSwitchDecision(allowed=True, status="allowed", mode="normal")

        if mode == "soft_pause":
            return KillSwitchDecision(
                allowed=False, 
                status="blocked", 
                reason="Kill switch is in soft_pause mode.", 
                mode="soft_pause"
            )
            
        if mode == "cancel_all":
            return KillSwitchDecision(
                allowed=False, 
                status="cancel_required", 
                reason="Kill switch is in cancel_all mode.", 
                mode="cancel_all",
                action_required="cancel_all"
            )
            
        if mode == "flatten_all":
            return KillSwitchDecision(
                allowed=False, 
                status="flatten_required", 
                reason="Kill switch is in flatten_all mode.", 
                mode="flatten_all",
                action_required="flatten_all"
            )
            
        if mode == "locked_down":
            return KillSwitchDecision(
                allowed=False, 
                status="locked_down", 
                reason=status.reason or "Kill switch is in locked_down mode. Explicit reset required.", 
                mode="locked_down"
            )

        # Unreachable while KillSwitchMode stays a closed Literal — which is exactly
        # why it must stay here. If a future mode is added and someone forgets a
        # branch above, the default is to BLOCK and report locked_down, not to fall
        # through to allowed. The safe answer to "I don't recognise this state" is no.
        return KillSwitchDecision(
            allowed=False,
            status="blocked",
            reason=f"Unknown kill switch mode: {mode}",
            mode="locked_down"
        )

    # --- Mode transitions ---

    def set_mode(self, mode: KillSwitchMode, reason: str, actor: str = "system"):
        # old_status is read purely so the audit event can record the transition as a
        # pair. "who moved the switch, from what, to what, and why" is the question an
        # incident review actually asks.
        old_status = self.state_manager.load()
        new_status = self.state_manager.save(mode, reason, actor)

        if self.audit_writer:
            self.audit_writer.write_event(
                "kill_switch_mode_changed",
                run_id=self.run_id,
                iteration=self.iteration,
                payload={
                    "old_mode": old_status.mode,
                    "new_mode": mode,
                    "reason": reason,
                    "actor": actor
                }
            )
        return new_status


# ==============================================================================
# LEGACY KILL SWITCH CONTROLLER
# ==============================================================================
#
# WARNING: this is a SECOND kill switch with a DIFFERENT mode vocabulary from
# AdvancedKillSwitch above:
#
#     AdvancedKillSwitch : normal | soft_pause | cancel_all | flatten_all | locked_down
#     KillSwitchController: soft | cancel | flatten        (+ an `enabled` flag)
#
# The two are not interchangeable and do not share state. The CLI wires
# KillSwitchController (see cli_safety.py); Telegram's /kill parses against
# KILL_SWITCH_MODES below. Before touching either, be sure which one your caller
# actually holds — the names are close enough to swap by accident.

# --- CONFIGURATIONS & CONSTANTS ---

KILL_SWITCH_MODES = ("soft", "cancel", "flatten")

# Severity ranking, used as a RATCHET in enable(): the switch may only be tightened,
# never loosened, while it is already armed. Escalating soft → flatten is allowed;
# quietly downgrading flatten → soft is not, because that would relax a brake someone
# pulled deliberately. Releasing it requires an explicit disable().
MODE_RANK = {"soft": 0, "cancel": 1, "flatten": 2}

AuditHook = Callable[[str, str, dict[str, Any]], None]


# --- Models ---

@dataclass(frozen=True)
class KillSwitchState:
    # `enabled` and `mode` are independent: mode says how hard to brake, enabled says
    # whether the brake is applied at all. A disabled state still carries a mode, which
    # is why the ratchet in enable() treats "not enabled" as rank -1 rather than reading
    # the stale mode.
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


# --- Controller ---

class KillSwitchController:

    # --- Construction ---

    def __init__(
        self,
        *,
        state_path: str | Path = "memory/kill_switch_state.json",
        enabled_flag_path: str | Path = "memory/kill_switch.enabled",
        lock_path: str | Path | None = None,
        audit_hook: AuditHook | None = None,
    ) -> None:
        self.state_path = Path(state_path)
        # A separate zero-byte marker file alongside the JSON state. Its mere existence
        # answers "is the switch on?" without parsing anything — so an external process,
        # a shell script or a monitoring probe can check the brake even if the JSON is
        # unreadable. The two are kept in step by _sync_enabled_flag().
        self.enabled_flag_path = Path(enabled_flag_path)
        self.lock_path = Path(lock_path) if lock_path is not None else self.state_path.with_suffix(
            self.state_path.suffix + ".lock"
        )
        self.audit_hook = audit_hook
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.enabled_flag_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        # Two layers of mutual exclusion: this RLock guards threads inside one process,
        # while the lock FILE guards concurrent `atlas` invocations. Both are needed —
        # the agent loop and a Telegram /kill can race across process boundaries.
        self._thread_lock = threading.RLock()

    # --- Read side ---

    def status(self) -> KillSwitchState:
        with self._locked():
            state = self._read_state()
            self._sync_enabled_flag(state.enabled)
            return state

    def is_enabled(self) -> bool:
        return self.status().enabled

    # --- Arming (ratchets only tighter) ---

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
        # Arguments are validated BEFORE the lock is taken and before any state is
        # written: a bad flatten strategy must fail loudly here, not halfway through
        # arming the switch and leaving it in a half-applied state.
        requested_mode = _normalize_mode(mode)
        if flatten_bps < 0:
            raise ValueError("flatten_bps must be non-negative")
        if flatten_strategy not in {"market", "aggressive_limit"}:
            raise ValueError(f"unsupported flatten strategy: {flatten_strategy}")
        with self._locked():
            previous = self._read_state()
            # rank -1 for a disabled switch: any requested mode outranks "off", so the
            # first enable() always takes effect regardless of the stale mode on disk.
            previous_rank = MODE_RANK[previous.mode] if previous.enabled else -1
            requested_rank = MODE_RANK[requested_mode]
            # The ratchet. Already braking at least this hard → no-op, and crucially we
            # do NOT re-run the cancel/flatten side effects. Re-flattening an already
            # flat account would place a second round of orders into the market.
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
            # State is persisted BEFORE the broker side effects run. If the flatten below
            # throws or the process dies mid-way, the switch is already armed on disk —
            # so we can crash while braking, but never crash back into "not braking".
            self._write_state(next_state)
            self._sync_enabled_flag(True)

            cancel_results: tuple[OrderResult, ...] = ()
            flatten_result: FlattenResult | None = None
            messages = [f"kill switch enabled ({requested_mode})"]

            # Each side effect fires only when the switch CROSSES that severity
            # threshold — `requested >= X` AND `previous < X`. This is what makes
            # escalation idempotent: going cancel → flatten runs the flatten only, and
            # does not re-issue the cancellations that already happened on the way in.
            if requested_rank >= MODE_RANK["cancel"] and previous_rank < MODE_RANK["cancel"]:
                cancel_results = self._run_cancel_actions(
                    broker=broker,
                    working_order_ids=working_order_ids,
                    cancel_working_orders=cancel_working_orders,
                )
                messages.append(
                    f"cancel attempted: {len(cancel_results)}"
                )
            # Note the ordering: cancel first, then flatten. Pulling resting orders before
            # closing positions stops a working order from filling into an account we are
            # in the middle of flattening, which would re-open exposure behind us.
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

    # --- Releasing ---

    def disable(
        self,
        *,
        reason: str = "",
        actor: str = "system",
    ) -> KillSwitchTransition:
        # The ONLY way out of an armed switch, and it is deliberately all-or-nothing:
        # there is no "step down one mode". Releasing a brake must be a single, explicit,
        # audited act rather than something that can happen gradually by accident.
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

    # --- Broker side effects ---

    def _run_cancel_actions(
        self,
        *,
        broker: Broker | None,
        working_order_ids: Sequence[str],
        cancel_working_orders: Callable[[], Sequence[OrderResult]] | None,
    ) -> tuple[OrderResult, ...]:
        # An injected callback wins over the broker path, so callers that already know
        # how to enumerate their working orders can supply it — and so tests can drive
        # the cancel path without a broker at all.
        if cancel_working_orders is not None:
            return tuple(cancel_working_orders())
        if broker is None or not working_order_ids:
            return ()
        # Dedup: the caller's id list may repeat, and cancelling the same order twice
        # invites a spurious "unknown order" error from the broker that would look like
        # a cancel failure in the audit trail.
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
        # A failed flatten is REPORTED, never raised. Raising here would unwind out of
        # enable() and abort the whole arming sequence — leaving the operator with an
        # exception and a switch they believe is on. Returning a failed FlattenResult
        # keeps the switch armed and makes the failure visible in the transition and
        # the audit trail, which is what someone staring at open positions needs.
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
            # Sanitised: raw broker exception text routinely carries request bodies and
            # credentials, and this message lands in the audit log.
            from atlas_agent.brokers.errors import make_broker_error
            broker_error = make_broker_error(
                operation="flatten_all", broker=broker, exc=exc
            )
            return FlattenResult(
                accepted=False,
                status="failed",
                message=broker_error.message,
                strategy=strategy,
                bps=bps,
                attempted=0,
                closed=0,
                failed=0,
            )

    # --- Mutual exclusion ---

    @contextmanager
    def _locked(self):
        # Thread lock OUTSIDE, file lock inside. The nesting order is fixed and matters:
        # taking them in the opposite order in some other code path would be a classic
        # lock-ordering deadlock. Both layers are needed because the agent loop, the CLI
        # and the Telegram bot can all reach for the switch at once — some in the same
        # process, some not.
        with self._thread_lock:
            with self.lock_path.open("a+", encoding="utf-8") as lock_file:
                _lock_file(lock_file)
                try:
                    yield
                finally:
                    _unlock_file(lock_file)

    # --- State I/O ---

    def _read_state(self) -> KillSwitchState:
        # The marker file is the backstop for the JSON. When the JSON is missing or
        # unparseable, its presence still proves the switch was armed, so we recover an
        # enabled state from it rather than assuming the brake is off.
        #
        # CAUTION — the recovered mode is hardcoded "soft", the WEAKEST setting. A switch
        # armed at "flatten" whose JSON is later corrupted therefore comes back as "soft":
        # still braking, but less hard than the operator asked for.
        #
        # CAUTION — note the failure policy when BOTH the JSON is unreadable and the marker
        # is absent: this returns disabled(), i.e. not braking. That is the opposite of
        # KillSwitchState.load() in safety/state.py, which escalates a corrupt file to
        # locked_down. The two kill switches disagree on what an unreadable safety file
        # means. Preserved here as-is; changing it is a behaviour change, not a comment.
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
        atomic_write_json(
            self.state_path,
            payload,
            indent=2,
            sort_keys=True,
        )

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
