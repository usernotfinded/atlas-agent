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
from atlas_agent.safety.kill_switch import KILL_SWITCH_MODES, KillSwitchController


Notifier = Callable[[str], Any]
AuditHook = Callable[[str, str, dict[str, Any]], Any]
TriggerHook = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True)
class DeadmanConfig:
    timeout_minutes: int = 0
    action: str = "soft"
    auto_reset: bool = True
    active_outside_market: bool = False
    check_interval_seconds: float = 5.0
    flatten_strategy: str = "market"
    flatten_bps: int = 25

    @property
    def enabled(self) -> bool:
        return self.timeout_minutes > 0

    @classmethod
    def from_env(cls) -> DeadmanConfig:
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
    target.parent.mkdir(parents=True, exist_ok=True)
    effective_now = now or datetime.now(UTC)
    payload = {
        "timestamp": effective_now.isoformat(),
        "source": source,
        "actor": actor,
    }
    temp_path = target.with_suffix(target.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    temp_path.replace(target)


def read_deadman_heartbeat(path: str | Path) -> HeartbeatRecord | None:
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
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return HeartbeatRecord(timestamp=timestamp, source=source, actor=actor)


class DeadmanSwitch:
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
        start = self._now()
        self._last_heartbeat_at = start
        self._last_heartbeat_source = "startup"
        self._triggered = False
        self._lock = threading.RLock()

    def record_heartbeat(
        self,
        *,
        source: str,
        actor: str = "system",
    ) -> None:
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

    async def run(
        self,
        *,
        stop_event: asyncio.Event | None = None,
        broker: Broker | None = None,
    ) -> None:
        while True:
            if stop_event is not None and stop_event.is_set():
                return
            await self.tick(broker=broker)
            if stop_event is not None and stop_event.is_set():
                return
            await self._sleep(self.config.check_interval_seconds)

    async def tick(self, *, broker: Broker | None = None) -> bool:
        if not self.config.enabled:
            return False
        self._refresh_from_external_heartbeat()
        now = self._now()
        market_state = self.market_detector.get_state(now)
        if not self.config.active_outside_market and market_state != "open":
            return False
        with self._lock:
            elapsed = now - self._last_heartbeat_at
            if self._triggered:
                return False
            if elapsed < timedelta(minutes=self.config.timeout_minutes):
                return False
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
