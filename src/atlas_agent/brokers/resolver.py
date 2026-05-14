from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from atlas_agent.brokers.base import Broker, BrokerProvider
from atlas_agent.brokers.paper import PaperBroker, PaperBrokerAdapter
from atlas_agent.portfolio.state import PortfolioState

if TYPE_CHECKING:
    from atlas_agent.config import AtlasConfig

if TYPE_CHECKING:
    from atlas_agent.config import AtlasConfig


@dataclass(frozen=True)
class BrokerStatus:
    mode: str
    broker_id: str
    configured: bool
    credentials_configured: bool
    can_sync: bool
    can_submit: bool
    code: str
    message: str

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "mode": self.mode,
            "broker_id": self.broker_id,
            "configured": self.configured,
            "credentials_configured": self.credentials_configured,
            "can_sync": self.can_sync,
            "can_submit": self.can_submit,
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class BrokerResolution:
    execution_broker: Broker | None
    sync_provider: BrokerProvider | None
    status: BrokerStatus


@dataclass(frozen=True)
class OptInStatus:
    valid: bool
    code: str
    message: str


class BrokerResolver:
    def __init__(self, config: AtlasConfig | None) -> None:
        self.config = config

    def resolve_status(self, mode: str) -> BrokerStatus:
        if mode == "paper":
            return BrokerStatus(
                mode="paper",
                broker_id="paper",
                configured=True,
                credentials_configured=True,
                can_sync=True,
                can_submit=True,
                code="paper_ready",
                message="paper broker is ready",
            )

        if mode != "live":
            return BrokerStatus(
                mode=mode,
                broker_id="unknown",
                configured=False,
                credentials_configured=False,
                can_sync=False,
                can_submit=False,
                code="unknown_mode",
                message=f"unsupported mode: {mode}",
            )

        # Live mode
        if self.config is None:
            return BrokerStatus(
                mode="live",
                broker_id="none",
                configured=False,
                credentials_configured=False,
                can_sync=False,
                can_submit=False,
                code="live_broker_unconfigured",
                message="live broker is not configured",
            )

        broker_id = self.config.live_broker
        if broker_id in {"", "none"}:
            return BrokerStatus(
                mode="live",
                broker_id="none",
                configured=False,
                credentials_configured=False,
                can_sync=False,
                can_submit=False,
                code="live_broker_unconfigured",
                message="live broker is not configured",
            )

        known_brokers = {"alpaca", "binance", "ccxt", "ibkr_stub"}
        if broker_id not in known_brokers:
            return BrokerStatus(
                mode="live",
                broker_id=broker_id,
                configured=False,
                credentials_configured=False,
                can_sync=False,
                can_submit=False,
                code="live_broker_unsupported",
                message="live broker is not supported",
            )

        creds_ok = self._credentials_configured(broker_id)
        if not creds_ok:
            return BrokerStatus(
                mode="live",
                broker_id=broker_id,
                configured=True,
                credentials_configured=False,
                can_sync=False,
                can_submit=False,
                code="live_credentials_missing",
                message="live broker credentials are missing",
            )

        if broker_id == "alpaca":
            can_sync = True
            can_submit, submit_code, submit_message = self._resolve_can_submit(broker_id)
            if can_submit:
                code = "live_ready"
                message = "live Alpaca sync and submit are ready"
            else:
                code = "live_sync_ready"
                message = f"live Alpaca sync is ready; submit {submit_message}"
            return BrokerStatus(
                mode="live",
                broker_id=broker_id,
                configured=True,
                credentials_configured=True,
                can_sync=can_sync,
                can_submit=can_submit,
                code=code,
                message=message,
            )

        return BrokerStatus(
            mode="live",
            broker_id=broker_id,
            configured=True,
            credentials_configured=True,
            can_sync=False,
            can_submit=False,
            code="live_sync_deferred",
            message="live broker is configured but sync and submit are deferred",
        )

    def _resolve_can_submit(self, broker_id: str) -> tuple[bool, str, str]:
        """Return (can_submit, code, message) for live submit.

        can_submit is true ONLY when ALL required conditions are satisfied.
        Any missing condition returns (False, reason_code, reason_message).
        """
        config = self.config
        if config is None:
            return False, "config_missing", "config is missing"

        # 1. Explicit opt-in flag
        if not config.broker.enable_live_submit:
            return False, "live_submit_disabled", "broker.enable_live_submit is false"

        # 2. Live trading must also be enabled (sync prerequisite)
        if not config.broker.enable_live_trading:
            return False, "live_trading_disabled", "broker.enable_live_trading is false"

        # 3. Kill switch must be normal
        from atlas_agent.safety.kill_switch import KillSwitchController
        try:
            ks = KillSwitchController(
                state_path=Path(config.memory_dir) / "kill_switch_state.json",
                enabled_flag_path=Path(config.memory_dir) / "kill_switch.enabled",
            )
            ks_status = ks.status()
            if ks_status.enabled and ks_status.mode != "normal":
                return False, "kill_switch_active", f"kill switch is {ks_status.mode}"
        except Exception:
            return False, "kill_switch_unreadable", "kill switch state is unreadable"

        # 4. Trading mode must be live
        if config.trading_mode != "live":
            return False, "trading_mode_not_live", f"trading_mode is {config.trading_mode}"

        # 5. Order approval mode must not disable live
        if config.safety.order_approval_mode == "disabled_live":
            return False, "approval_disabled", "order_approval_mode disables live trading"

        # 6. Leverage must be disabled (explicit review required)
        if config.risk.allow_leverage:
            return False, "leverage_enabled", "allow_leverage is true"

        # 7. Credentials must be configured
        if not self._credentials_configured(broker_id):
            return False, "credentials_missing", "live broker credentials are missing"

        # 8. Audit/opt-in state record
        opt_in = _live_submit_opt_in_status(config)
        if not opt_in.valid:
            return False, opt_in.code, opt_in.message

        return True, "live_submit_ready", "ready"

    def resolve_sync_provider(self, mode: str) -> BrokerResolution:
        status = self.resolve_status(mode)
        if mode == "paper":
            cash = self.config.starting_cash if self.config else 10000.0
            paper = PaperBroker(state=PortfolioState(cash=cash))
            adapter = PaperBrokerAdapter(broker=paper)
            return BrokerResolution(
                execution_broker=paper,
                sync_provider=adapter,
                status=status,
            )
        if mode == "live" and status.broker_id == "alpaca" and status.can_sync:
            from atlas_agent.brokers.alpaca import AlpacaBrokerAdapter
            return BrokerResolution(
                execution_broker=None,
                sync_provider=AlpacaBrokerAdapter(config=self.config),
                status=status,
            )
        # Live unsupported or unknown: None
        return BrokerResolution(
            execution_broker=None,
            sync_provider=None,
            status=status,
        )

    def resolve_execution_broker(self, mode: str) -> BrokerResolution:
        status = self.resolve_status(mode)
        if mode == "paper":
            cash = self.config.starting_cash if self.config else 10000.0
            paper = PaperBroker(state=PortfolioState(cash=cash))
            adapter = PaperBrokerAdapter(broker=paper)
            return BrokerResolution(
                execution_broker=paper,
                sync_provider=adapter,
                status=status,
            )
        # Live: only return execution broker if can_submit is true
        if mode == "live" and status.can_submit and status.broker_id == "alpaca":
            from atlas_agent.brokers.alpaca import AlpacaBroker
            return BrokerResolution(
                execution_broker=AlpacaBroker(config=self.config),
                sync_provider=None,
                status=status,
            )
        return BrokerResolution(
            execution_broker=None,
            sync_provider=None,
            status=status,
        )

    def _credentials_configured(self, broker_id: str) -> bool:
        if broker_id == "alpaca":
            return bool(os.getenv("ALPACA_API_KEY")) and bool(os.getenv("ALPACA_SECRET_KEY"))
        if broker_id == "binance":
            binance_secret = os.getenv("BINANCE_API_SECRET") or os.getenv("BINANCE_SECRET_KEY")
            return bool(os.getenv("BINANCE_API_KEY")) and bool(binance_secret)
        if broker_id == "ccxt":
            return bool(os.getenv("CCXT_API_KEY")) or bool(os.getenv("EXCHANGE_API_KEY"))
        return False


def _compute_live_submit_fingerprint(config: AtlasConfig) -> str:
    """Deterministic fingerprint of live-submit config for opt-in validation."""
    parts = [
        config.broker.provider,
        str(config.risk.live_submit_max_order_notional or config.risk.max_order_notional),
    ]
    symbols = config.risk.live_submit_allowed_symbols or config.risk.symbol_allowlist
    if symbols is not None:
        parts.append(",".join(sorted(s.upper() for s in symbols)))
    sides = config.risk.live_submit_allowed_sides
    if sides is not None:
        parts.append(",".join(sorted(s.lower() for s in sides)))
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _live_submit_opt_in_status(config: AtlasConfig) -> OptInStatus:
    """Validate the live-submit opt-in record.

    The opt-in is valid ONLY if ALL of the following are true:

    1. The file audit/live_submit_opt_in.jsonl exists.
    2. The latest record has event_type == "live_submit_opt_in_enabled".
    3. The latest record has opt_in == true.
    4. The latest record's broker_id matches config.broker.provider.
    5. The latest record's config_fingerprint matches the current live-submit
       config fingerprint.
    6. The latest record's created_at is a parseable ISO datetime.
    7. No subsequent record with event_type == "live_submit_opt_in_disabled"
       exists after the latest enabled record.
    8. (Optional) The opt-in has not expired (default 24h from created_at).

    If any condition fails, return OptInStatus(valid=False, code=..., message=...).
    """
    opt_in_path = Path(config.audit_dir) / "live_submit_opt_in.jsonl"
    if not opt_in_path.exists():
        return OptInStatus(False, "opt_in_file_missing", "live submit opt-in file does not exist")

    # Read all lines, find latest enabled and latest disabled
    latest_enabled: dict | None = None
    latest_disabled: dict | None = None
    try:
        text = opt_in_path.read_text(encoding="utf-8").strip()
    except Exception:
        return OptInStatus(False, "opt_in_file_unreadable", "live submit opt-in file is unreadable")

    for line in text.split("\n"):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        et = record.get("event_type")
        if et == "live_submit_opt_in_enabled":
            latest_enabled = record
        elif et == "live_submit_opt_in_disabled":
            latest_disabled = record

    if latest_enabled is None:
        return OptInStatus(False, "opt_in_never_enabled", "no live_submit_opt_in_enabled record found")

    # Condition 6: parseable created_at
    try:
        enabled_at = datetime.fromisoformat(latest_enabled["created_at"])
    except (KeyError, ValueError, TypeError):
        return OptInStatus(False, "opt_in_invalid_timestamp", "live submit opt-in has invalid created_at")

    # Condition 7: no subsequent disable after enable
    if latest_disabled is not None:
        try:
            disabled_at = datetime.fromisoformat(latest_disabled["created_at"])
        except (KeyError, ValueError, TypeError):
            pass  # malformed disable record; ignore it
        else:
            if disabled_at >= enabled_at:
                return OptInStatus(False, "opt_in_disabled", "live submit opt-in was subsequently disabled")

    # Condition 4: broker_id matches
    if latest_enabled.get("broker_id") != config.broker.provider:
        return OptInStatus(False, "opt_in_broker_mismatch", "opt-in broker_id does not match current broker")

    # Condition 5: config fingerprint matches
    current_fp = _compute_live_submit_fingerprint(config)
    if latest_enabled.get("config_fingerprint") != current_fp:
        return OptInStatus(False, "opt_in_config_changed", "live submit config changed since opt-in")

    # Condition 8: expiry (default 24h)
    expiry_hours = float(latest_enabled.get("expiry_hours", 24))
    if datetime.now(UTC) > enabled_at + timedelta(hours=expiry_hours):
        return OptInStatus(False, "opt_in_expired", "live submit opt-in has expired")

    return OptInStatus(True, "opt_in_valid", "live submit opt-in is valid")
