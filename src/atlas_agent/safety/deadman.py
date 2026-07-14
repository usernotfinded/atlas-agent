# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    safety/deadman.py
# PURPOSE: The dead-man's switch. Watches the heartbeat and trips the kill switch
#          when the agent stops proving it is alive. This is the brake that works
#          when nothing else can: it defends against the agent CRASHING with open
#          positions, which is exactly the case where the agent cannot save itself.
# DEPS:    safety.kill_switch (what it trips), market.session (when it is armed),
#          safety.atomic_write (heartbeat persistence)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import asyncio
import inspect
import os
import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable

from atlas_agent.brokers.base import Broker
from atlas_agent.config import parse_bool
from atlas_agent.market.session import MarketSessionDetector
from atlas_agent.safety.atomic_write import atomic_write_json
from atlas_agent.safety.kill_switch import KILL_SWITCH_MODES, KillSwitchController


# --- CONFIGURATIONS & CONSTANTS ---

Notifier = Callable[[str], Any]
AuditHook = Callable[[str, str, dict[str, Any]], Any]
TriggerHook = Callable[[dict[str, Any]], Any]


# ==============================================================================
# CONFIGURATION
# ==============================================================================

@dataclass(frozen=True)
class DeadmanConfig:
    # timeout_minutes=0 means DISABLED (see `enabled` below). Off by default, because
    # a deadman that trips spuriously would flatten a healthy book — the cure being
    # worse than the disease. Enabling it is a deliberate act.
    timeout_minutes: int = 0
    action: str = "soft"
    auto_reset: bool = True

    # Off by default: outside market hours a "dead" agent cannot do any harm, since no
    # order would fill anyway. Arming it then would only generate false alarms.
    active_outside_market: bool = False
    check_interval_seconds: float = 5.0
    flatten_strategy: str = "market"
    flatten_bps: int = 25

    @property
    def enabled(self) -> bool:
        return self.timeout_minutes > 0

    @classmethod
    def from_env(cls) -> DeadmanConfig:
        # Every value is validated here, at construction, and an invalid one RAISES
        # rather than falling back to a default. A deadman configured with a typo must
        # refuse to start — silently running with `action="soft"` when the operator
        # asked for "flatten" is the kind of surprise this module exists to eliminate.
        timeout_raw = os.getenv("DEADMAN_TIMEOUT_MINUTES", "").strip()
        timeout_minutes = int(timeout_raw) if timeout_raw else 0
        action = os.getenv("DEADMAN_ACTION", "soft").strip().lower()
        if action not in KILL_SWITCH_MODES:
            raise ValueError(
                "DEADMAN_ACTION must be one of: " + ", ".join(KILL_SWITCH_MODES)
            )
        auto_reset = parse_bool(os.getenv("DEADMAN_AUTO_RESET"), default=True)
        active_outside_market = parse_bool(
            os.getenv("DEADMAN_ACTIVE_OUTSIDE_MARKET"),
            default=False,
        )
        check_interval_raw = os.getenv("DEADMAN_CHECK_INTERVAL_SECONDS", "").strip()
        check_interval_seconds = float(check_interval_raw) if check_interval_raw else 5.0
        flatten_strategy = os.getenv("DEADMAN_FLATTEN_STRATEGY", "market").strip().lower()
        if flatten_strategy not in {"market", "aggressive_limit"}:
            raise ValueError(
                "DEADMAN_FLATTEN_STRATEGY must be market or aggressive_limit"
            )
        flatten_bps_raw = os.getenv("DEADMAN_FLATTEN_BPS", "").strip()
        flatten_bps = int(flatten_bps_raw) if flatten_bps_raw else 25
        if timeout_minutes < 0:
            raise ValueError("DEADMAN_TIMEOUT_MINUTES cannot be negative")
        if check_interval_seconds <= 0:
            raise ValueError("DEADMAN_CHECK_INTERVAL_SECONDS must be positive")
        if flatten_bps < 0:
            raise ValueError("DEADMAN_FLATTEN_BPS cannot be negative")
        return cls(
            timeout_minutes=timeout_minutes,
            action=action,
            auto_reset=auto_reset,
            active_outside_market=active_outside_market,
            check_interval_seconds=check_interval_seconds,
            flatten_strategy=flatten_strategy,
            flatten_bps=flatten_bps,
        )


# ==============================================================================
# HEARTBEAT MODELS
# ==============================================================================

@dataclass(frozen=True)
class HeartbeatStatus:
    enabled: bool
    action: str
    timeout_minutes: int
    last_heartbeat_at: str
    last_heartbeat_source: str
    seconds_since_heartbeat: int
    market_state: str
    triggered: bool


@dataclass(frozen=True)
class HeartbeatRecord:
    timestamp: datetime
    source: str
    actor: str


# ==============================================================================
# HEARTBEAT FILE I/O
# ==============================================================================
#
# The file is the CROSS-PROCESS channel. An external supervisor, a cron job or a
# separate `atlas` invocation can stamp it, which is what allows a deadman running
# in one process to be fed by an agent running in another.

def deadman_heartbeat_path(memory_dir: Path) -> Path:
    return memory_dir / "deadman_heartbeat.json"


def write_deadman_heartbeat(
    path: str | Path,
    *,
    source: str,
    actor: str,
    now: datetime | None = None,
) -> None:
    target = Path(path)
    effective_now = now or datetime.now(UTC)
    payload = {
        "timestamp": effective_now.isoformat(),
        "source": source,
        "actor": actor,
    }
    atomic_write_json(
        target,
        payload,
        sort_keys=True,
    )


def read_deadman_heartbeat(path: str | Path) -> HeartbeatRecord | None:
    """Read the external heartbeat file, or None if it is absent or unusable.

    Returns:
        A HeartbeatRecord, or None. None means "no usable heartbeat here" — the
        caller must treat that as an ABSENCE of a fresh signal, never as a fresh one.
        Every failure path below therefore returns None rather than a synthesised
        record with the current time, which would silently feed the deadman a
        heartbeat the agent never sent.
    """
    target = Path(path)
    if not target.exists():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    timestamp_raw = payload.get("timestamp")
    source = str(payload.get("source", "")).strip()
    actor = str(payload.get("actor", "")).strip()
    # The timestamp is the only field that MUST parse — it is the one the freshness
    # check depends on. source/actor are provenance labels and degrade to placeholders.
    if not isinstance(timestamp_raw, str) or not timestamp_raw:
        return None
    try:
        timestamp = datetime.fromisoformat(timestamp_raw)
    except ValueError:
        return None
    if not source:
        source = "external"
    if not actor:
        actor = "unknown"
    # A naive timestamp is assumed UTC. Comparing naive to aware datetimes raises, and
    # an exception inside the deadman's watch loop is the last thing anyone wants.
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return HeartbeatRecord(timestamp=timestamp, source=source, actor=actor)


# ==============================================================================
# DEADMAN SWITCH
# ==============================================================================

class DeadmanSwitch:

    # --- Construction ---

    def __init__(
        self,
        *,
        kill_switch: KillSwitchController,
        config: DeadmanConfig | None = None,
        market_detector: MarketSessionDetector | None = None,
        notifiers: list[Notifier] | None = None,
        audit_hook: AuditHook | None = None,
        trigger_hook: TriggerHook | None = None,
        heartbeat_path: str | Path | None = None,
        now_func: Callable[[], datetime] | None = None,
        sleep_func: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.kill_switch = kill_switch
        self.config = config or DeadmanConfig.from_env()
        self.market_detector = market_detector or MarketSessionDetector()
        self.notifiers = list(notifiers or [])
        self.audit_hook = audit_hook
        self.trigger_hook = trigger_hook
        self.heartbeat_path = Path(heartbeat_path) if heartbeat_path is not None else None
        self._now = now_func or (lambda: datetime.now(UTC))
        self._sleep = sleep_func or asyncio.sleep
        # Construction itself counts as a heartbeat. Without this the switch would be
        # born already `timeout_minutes` overdue and would trip on its very first tick.
        start = self._now()
        self._last_heartbeat_at = start
        self._last_heartbeat_source = "startup"
        self._triggered = False
        self._lock = threading.RLock()

    # --- Heartbeat recording ---

    def record_heartbeat(
        self,
        *,
        source: str,
        actor: str = "system",
    ) -> None:
        # Clearing `_triggered` here is what makes the switch re-armable: once the agent
        # proves it is alive again, the deadman goes back on watch. Note this does NOT
        # release the kill switch it tripped — that stays armed until a human disables
        # it, which is the whole point of a deadman.
        with self._lock:
            now = self._now()
            self._last_heartbeat_at = now
            self._last_heartbeat_source = source
            self._triggered = False
        if self.heartbeat_path is not None:
            write_deadman_heartbeat(
                self.heartbeat_path,
                source=source,
                actor=actor,
                now=now,
            )
        self._call_audit_sync(
            "deadman_heartbeat",
            actor,
            {"source": source, "timestamp": now.isoformat()},
        )

    def record_interaction(
        self,
        *,
        source: str,
        actor: str = "user",
    ) -> bool:
        if not self.config.auto_reset:
            return False
        self.record_heartbeat(source=source, actor=actor)
        return True

    # --- Observation ---

    def status(self) -> HeartbeatStatus:
        self._refresh_from_external_heartbeat()
        now = self._now()
        with self._lock:
            last_heartbeat_at = self._last_heartbeat_at
            last_source = self._last_heartbeat_source
            triggered = self._triggered
        elapsed = max(int((now - last_heartbeat_at).total_seconds()), 0)
        market_state = self.market_detector.get_state(now)
        return HeartbeatStatus(
            enabled=self.config.enabled,
            action=self.config.action,
            timeout_minutes=self.config.timeout_minutes,
            last_heartbeat_at=last_heartbeat_at.isoformat(),
            last_heartbeat_source=last_source,
            seconds_since_heartbeat=elapsed,
            market_state=market_state,
            triggered=triggered,
        )

    # ==========================================================================
    # WATCH LOOP
    # ==========================================================================

    async def run(
        self,
        *,
        stop_event: asyncio.Event | None = None,
        broker: Broker | None = None,
    ) -> None:
        # stop_event is checked twice per iteration — before and after the tick — so a
        # shutdown requested *during* a tick does not cost a full sleep interval before
        # it is honoured.
        while True:
            if stop_event is not None and stop_event.is_set():
                return
            await self.tick(broker=broker)
            if stop_event is not None and stop_event.is_set():
                return
            await self._sleep(self.config.check_interval_seconds)

    async def tick(self, *, broker: Broker | None = None) -> bool:
        """One watch cycle. Returns True only if this call tripped the switch."""
        # Four gates in order, cheapest and least destructive first. Every one of them
        # is a reason NOT to trip — reaching the bottom is what trips it.

        # 1. Disabled → nothing to do.
        if not self.config.enabled:
            return False

        # 2. Pick up a heartbeat written by another process before judging staleness,
        #    otherwise a healthy agent in a separate process looks dead from here.
        self._refresh_from_external_heartbeat()
        now = self._now()
        market_state = self.market_detector.get_state(now)

        # 3. Market closed → stand down. A dead agent outside market hours holds no
        #    live risk, and flattening into a closed book achieves nothing but noise.
        if not self.config.active_outside_market and market_state != "open":
            return False

        with self._lock:
            elapsed = now - self._last_heartbeat_at
            # 4a. Already tripped → return False rather than re-trip. This is the latch
            #     that stops the loop from re-issuing flatten orders every 5 seconds
            #     into an account it has already flattened.
            if self._triggered:
                return False
            # 4b. Heartbeat still fresh → the agent is alive.
            if elapsed < timedelta(minutes=self.config.timeout_minutes):
                return False
            # Latch set INSIDE the lock, before the (slow, awaited) kill-switch call
            # below. Otherwise two concurrent ticks could both pass the check and both
            # fire the brake.
            self._triggered = True
            last_heartbeat = self._last_heartbeat_at.isoformat()
            last_source = self._last_heartbeat_source
        reason = (
            "deadman timeout elapsed"
            f" ({self.config.timeout_minutes}m);"
            f" last heartbeat={last_heartbeat};"
            f" source={last_source};"
            f" market_state={market_state}"
        )
        transition = self.kill_switch.enable(
            mode=self.config.action,
            reason=reason,
            actor="deadman",
            broker=broker,
            flatten_strategy=self.config.flatten_strategy,
            flatten_bps=self.config.flatten_bps,
        )
        trigger_payload = {
            "mode": self.config.action,
            "reason": reason,
            "market_state": market_state,
            "changed": transition.changed,
        }
        await self._call_trigger_hook(trigger_payload)
        await self._notify_all(
            "Dead man's switch activated: "
            f"mode={self.config.action}; reason={reason}; changed={transition.changed}"
        )
        await self._call_audit_async(
            "deadman_triggered",
            "deadman",
            trigger_payload,
        )
        return True

    def _refresh_from_external_heartbeat(self) -> None:
        if self.heartbeat_path is None:
            return
        external = read_deadman_heartbeat(self.heartbeat_path)
        if external is None:
            return
        with self._lock:
            if external.timestamp <= self._last_heartbeat_at:
                return
            self._last_heartbeat_at = external.timestamp
            self._last_heartbeat_source = external.source
            self._triggered = False
        self._call_audit_sync(
            "deadman_heartbeat_external",
            external.actor,
            {
                "source": external.source,
                "timestamp": external.timestamp.isoformat(),
            },
        )

    async def _notify_all(self, message: str) -> None:
        for notify in self.notifiers:
            try:
                result = notify(message)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                continue

    async def _call_audit_async(
        self,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
    ) -> None:
        if self.audit_hook is None:
            return
        try:
            result = self.audit_hook(event_type, actor, payload)
            if inspect.isawaitable(result):
                await result
        except Exception:
            return

    def _call_audit_sync(
        self,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
    ) -> None:
        if self.audit_hook is None:
            return
        try:
            result = self.audit_hook(event_type, actor, payload)
            if inspect.isawaitable(result):
                return
        except Exception:
            return

    async def _call_trigger_hook(self, payload: dict[str, Any]) -> None:
        if self.trigger_hook is None:
            return
        try:
            result = self.trigger_hook(payload)
            if inspect.isawaitable(result):
                await result
        except Exception:
            return
