from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskLimits:
    max_daily_loss: float = 100.0
    max_position_size: float = 100.0
    max_trades_per_day: int = 5
    max_portfolio_exposure: float = 1_000.0
    max_order_notional: float = 100.0
    allow_leverage: bool = False
    minimum_confidence: float = 0.55
    require_stop_loss_live: bool = True
    enforce_market_hours: bool = False
    symbol_allowlist: set[str] | None = None
    symbol_blocklist: set[str] | None = None

