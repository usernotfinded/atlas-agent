from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


TRUE_VALUES = {"1", "true", "t", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "f", "no", "n", "off"}


def parse_bool(value: str | bool | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


def parse_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    value = float(raw)
    if value < 0:
        raise ValueError(f"{name} cannot be negative")
    return value


def parse_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    value = int(raw)
    if value < 0:
        raise ValueError(f"{name} cannot be negative")
    return value


def parse_csv_set(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip().upper() for item in value.split(",") if item.strip()}


@dataclass(frozen=True)
class AtlasConfig:
    trading_mode: str = "paper"
    enable_live_trading: bool = False
    live_broker: str = "none"
    order_approval_mode: str = "manual_live"
    require_order_approval: bool = True
    max_daily_loss: float = 100.0
    max_position_size: float = 100.0
    max_trades_per_day: int = 5
    max_portfolio_exposure: float = 1_000.0
    max_order_notional: float = 100.0
    allow_leverage: bool = False
    kill_switch_enabled: bool = False
    minimum_confidence: float = 0.55
    require_stop_loss_live: bool = True
    enforce_market_hours: bool = False
    symbol_allowlist: set[str] | None = None
    symbol_blocklist: set[str] | None = None
    starting_cash: float = 10_000.0
    default_symbol: str = "BTC-USD"
    data_path: Path = Path("data/sample/ohlcv.csv")
    memory_dir: Path = Path("memory")
    audit_dir: Path = Path("audit")
    pending_orders_dir: Path = Path("pending_orders")
    reports_dir: Path = Path("reports")
    events_dir: Path = Path("events")
    allow_git_commit: bool = False
    allow_git_push: bool = False
    git_commit_author_name: str = "Atlas Agent"
    git_commit_author_email: str = "atlas-agent@example.local"

    @classmethod
    def from_env(cls) -> AtlasConfig:
        mode = os.getenv("TRADING_MODE", "paper").strip().lower()
        if mode not in {"backtest", "paper", "live"}:
            raise ValueError("TRADING_MODE must be backtest, paper, or live")
        approval_mode = os.getenv("ORDER_APPROVAL_MODE", "manual_live").strip().lower()
        if approval_mode not in {"auto_paper", "manual_live", "disabled_live"}:
            raise ValueError("ORDER_APPROVAL_MODE is invalid")
        return cls(
            trading_mode=mode,
            enable_live_trading=parse_bool(os.getenv("ENABLE_LIVE_TRADING"), default=False),
            live_broker=os.getenv("LIVE_BROKER", "none").strip().lower(),
            order_approval_mode=approval_mode,
            require_order_approval=parse_bool(
                os.getenv("REQUIRE_ORDER_APPROVAL"), default=True
            ),
            max_daily_loss=parse_float("MAX_DAILY_LOSS", 100.0),
            max_position_size=parse_float("MAX_POSITION_SIZE", 100.0),
            max_trades_per_day=parse_int("MAX_TRADES_PER_DAY", 5),
            max_portfolio_exposure=parse_float("MAX_PORTFOLIO_EXPOSURE", 1_000.0),
            max_order_notional=parse_float("MAX_ORDER_NOTIONAL", 100.0),
            allow_leverage=parse_bool(os.getenv("ALLOW_LEVERAGE"), default=False),
            kill_switch_enabled=parse_bool(os.getenv("KILL_SWITCH_ENABLED"), default=False),
            minimum_confidence=parse_float("MINIMUM_CONFIDENCE", 0.55),
            require_stop_loss_live=parse_bool(
                os.getenv("REQUIRE_STOP_LOSS_LIVE"), default=True
            ),
            enforce_market_hours=parse_bool(
                os.getenv("ENFORCE_MARKET_HOURS"), default=False
            ),
            symbol_allowlist=parse_csv_set(os.getenv("SYMBOL_ALLOWLIST")) or None,
            symbol_blocklist=parse_csv_set(os.getenv("SYMBOL_BLOCKLIST")) or None,
            starting_cash=parse_float("STARTING_CASH", 10_000.0),
            default_symbol=os.getenv("DEFAULT_SYMBOL", "BTC-USD").strip().upper(),
            data_path=Path(os.getenv("DATA_PATH", "data/sample/ohlcv.csv")),
            memory_dir=Path(os.getenv("MEMORY_DIR", "memory")),
            audit_dir=Path(os.getenv("AUDIT_DIR", "audit")),
            pending_orders_dir=Path(os.getenv("PENDING_ORDERS_DIR", "pending_orders")),
            reports_dir=Path(os.getenv("REPORTS_DIR", "reports")),
            events_dir=Path(os.getenv("EVENTS_DIR", "events")),
            allow_git_commit=parse_bool(os.getenv("ALLOW_GIT_COMMIT"), default=False),
            allow_git_push=parse_bool(os.getenv("ALLOW_GIT_PUSH"), default=False),
            git_commit_author_name=os.getenv(
                "GIT_COMMIT_AUTHOR_NAME",
                "Atlas Agent",
            ),
            git_commit_author_email=os.getenv(
                "GIT_COMMIT_AUTHOR_EMAIL",
                "atlas-agent@example.local",
            ),
        )

    def live_disabled_reasons(self) -> tuple[str, ...]:
        reasons: list[str] = []
        if self.trading_mode != "live":
            reasons.append("TRADING_MODE must be live")
        if not self.enable_live_trading:
            reasons.append("ENABLE_LIVE_TRADING must be true")
        if self.live_broker in {"", "none"}:
            reasons.append("LIVE_BROKER must name a supported live broker")
        if self.order_approval_mode == "disabled_live":
            reasons.append("ORDER_APPROVAL_MODE disables live trading")
        if self.kill_switch_enabled:
            reasons.append("KILL_SWITCH_ENABLED is true")
        if self.allow_leverage:
            reasons.append("ALLOW_LEVERAGE must remain false unless explicitly reviewed")
        return tuple(reasons)

    def ensure_dirs(self) -> None:
        for path in (
            self.memory_dir,
            self.audit_dir,
            self.pending_orders_dir,
            self.reports_dir,
            self.events_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
