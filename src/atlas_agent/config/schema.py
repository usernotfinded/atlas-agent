from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional, Set

from pydantic import BaseModel, Field, SecretStr, model_validator


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


class ModelConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o"
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None
    timeout: float = 30.0
    max_retries: int = 3
    temperature: float = 0.0


class ProviderConfig(BaseModel):
    openai: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="openai", model="gpt-4o"))
    anthropic: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="anthropic", model="claude-3-5-sonnet-20240620"))
    openrouter: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="openrouter", model="anthropic/claude-3.5-sonnet"))
    local: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="local", model="llama3"))


class BrokerConfig(BaseModel):
    provider: str = "none"
    enable_live_trading: bool = False
    paper_broker_default: str = "paper"
    # Note: credential keys are stored here as names of env vars, not values


class RiskConfig(BaseModel):
    max_daily_loss: float = 100.0
    max_position_notional: float = 100.0
    max_trades_per_day: int = 5
    max_portfolio_exposure: float = 1000.0
    max_order_notional: float = 100.0
    allow_leverage: bool = False
    minimum_confidence: float = 0.55
    require_stop_loss_live: bool = True
    enforce_market_hours: bool = False
    symbol_allowlist: Optional[Set[str]] = None
    symbol_blocklist: Optional[Set[str]] = None


class SafetyConfig(BaseModel):
    kill_switch_enabled: bool = False
    heartbeat_timeout_seconds: int = 300
    require_order_approval: bool = True
    order_approval_mode: str = "manual_live" # auto_paper, manual_live, disabled_live


class AuditConfig(BaseModel):
    enabled: bool = True
    redact_secrets: bool = True
    audit_dir: Path = Path("audit")


class DashboardConfig(BaseModel):
    enabled: bool = True
    port: int = 8080
    host: str = "127.0.0.1"


class BacktestConfig(BaseModel):
    initial_cash: float = 10000.0
    default_symbol: str = "BTC-USD"
    data_path: Path = Path("data/sample/ohlcv.csv")
    reports_dir: Path = Path("reports/backtest")


class UpdateConfig(BaseModel):
    auto_check: str = "daily" # daily, weekly, never
    auto_apply: bool = False


class AtlasConfig(BaseModel):
    trading_mode: str = "paper" # backtest, paper, live
    workspace_root: Path = Path(".")
    memory_dir: Path = Path("memory")
    reports_dir: Path = Path("reports")
    events_dir: Path = Path("events")
    pending_orders_dir: Path = Path("pending_orders")
    
    model: ModelConfig = Field(default_factory=ModelConfig)
    providers: ProviderConfig = Field(default_factory=ProviderConfig)
    broker: BrokerConfig = Field(default_factory=BrokerConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
    update: UpdateConfig = Field(default_factory=UpdateConfig)

    # Git settings
    allow_git_commit: bool = False
    allow_git_push: bool = False
    git_commit_author_name: str = "Atlas Agent"
    git_commit_author_email: str = "atlas-agent@example.local"

    @model_validator(mode='before')
    @classmethod
    def map_legacy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        
        # Helper to set nested values
        def set_nested(d, path, val):
            parts = path.split('.')
            curr = d
            for p in parts[:-1]:
                if p not in curr:
                    curr[p] = {}
                curr = curr[p]
            curr[parts[-1]] = val

        mapping = {
            "enable_live_trading": "broker.enable_live_trading",
            "live_broker": "broker.provider",
            "order_approval_mode": "safety.order_approval_mode",
            "require_order_approval": "safety.require_order_approval",
            "max_daily_loss": "risk.max_daily_loss",
            "max_position_size": "risk.max_position_notional",
            "max_trades_per_day": "risk.max_trades_per_day",
            "max_portfolio_exposure": "risk.max_portfolio_exposure",
            "max_order_notional": "risk.max_order_notional",
            "allow_leverage": "risk.allow_leverage",
            "kill_switch_enabled": "safety.kill_switch_enabled",
            "minimum_confidence": "risk.minimum_confidence",
            "require_stop_loss_live": "risk.require_stop_loss_live",
            "enforce_market_hours": "risk.enforce_market_hours",
            "symbol_allowlist": "risk.symbol_allowlist",
            "symbol_blocklist": "risk.symbol_blocklist",
            "starting_cash": "backtest.initial_cash",
            "default_symbol": "backtest.default_symbol",
            "data_path": "backtest.data_path",
            "audit_dir": "audit.audit_dir",
        }

        for legacy_key, new_path in mapping.items():
            if legacy_key in data:
                val = data.pop(legacy_key)
                # Avoid overwriting if new_path already has a value in data
                # but legacy fields should take precedence for compatibility in constructor
                set_nested(data, new_path, val)
        
        return data

    # Compatibility properties
    @property
    def enable_live_trading(self) -> bool:
        return self.broker.enable_live_trading
    
    @property
    def live_broker(self) -> str:
        return self.broker.provider
    
    @property
    def order_approval_mode(self) -> str:
        return self.safety.order_approval_mode
    
    @property
    def require_order_approval(self) -> bool:
        return self.safety.require_order_approval
    
    @property
    def max_daily_loss(self) -> float:
        return self.risk.max_daily_loss
    
    @property
    def max_position_size(self) -> float:
        return self.risk.max_position_notional
    
    @property
    def max_trades_per_day(self) -> int:
        return self.risk.max_trades_per_day
    
    @property
    def max_portfolio_exposure(self) -> float:
        return self.risk.max_portfolio_exposure
    
    @property
    def max_order_notional(self) -> float:
        return self.risk.max_order_notional
    
    @property
    def allow_leverage(self) -> bool:
        return self.risk.allow_leverage
    
    @property
    def kill_switch_enabled(self) -> bool:
        return self.safety.kill_switch_enabled
    
    @property
    def minimum_confidence(self) -> float:
        return self.risk.minimum_confidence
    
    @property
    def require_stop_loss_live(self) -> bool:
        return self.risk.require_stop_loss_live
    
    @property
    def enforce_market_hours(self) -> bool:
        return self.risk.enforce_market_hours
    
    @property
    def symbol_allowlist(self) -> Optional[Set[str]]:
        return self.risk.symbol_allowlist
    
    @property
    def symbol_blocklist(self) -> Optional[Set[str]]:
        return self.risk.symbol_blocklist
    
    @property
    def starting_cash(self) -> float:
        return self.backtest.initial_cash
    
    @property
    def default_symbol(self) -> str:
        return self.backtest.default_symbol
    
    @property
    def data_path(self) -> Path:
        return self.backtest.data_path
    
    @property
    def audit_dir(self) -> Path:
        return self.audit.audit_dir

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_env(cls) -> AtlasConfig:
        """Compatibility method to load config using the new system but called from old code."""
        from atlas_agent.config.store import get_config
        return get_config()

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
            self.audit.audit_dir,
            self.pending_orders_dir,
            self.reports_dir,
            self.events_dir,
            self.backtest.reports_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
