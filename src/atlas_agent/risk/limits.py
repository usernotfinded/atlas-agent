from __future__ import annotations

from typing import Optional, Set
from pydantic import BaseModel, Field


class RiskLimits(BaseModel):
    max_position_notional: float = Field(default=1000.0, description="Max notional value for a single position")
    max_symbol_exposure_pct: float = Field(default=0.25, description="Max exposure to a single symbol as % of equity")
    max_portfolio_exposure_pct: float = Field(default=1.0, description="Max total portfolio exposure as % of equity")
    max_single_trade_notional: float = Field(default=500.0, description="Max notional value for a single trade")
    max_daily_loss_pct: float = Field(default=0.02, description="Max daily loss as % of equity")
    max_open_positions: int = Field(default=10, description="Max number of concurrent open positions")
    
    allowed_symbols: Optional[Set[str]] = Field(default=None, description="Set of symbols allowed for trading. None means all.")
    blocked_symbols: Set[str] = Field(default_factory=set, description="Set of symbols explicitly blocked.")
    
    paper_only: bool = Field(default=True, description="If true, only paper trading is allowed.")
    live_trading_enabled: bool = Field(default=False, description="Explicit flag to enable live trading.")
    
    minimum_confidence: float = Field(default=0.6, description="Minimum model confidence required for execution.")
    require_stop_loss_live: bool = Field(default=True, description="Require a stop loss for live orders.")
    allow_shorting: bool = Field(default=False, description="Allow opening or flipping to short positions.")


DEFAULT_RISK_LIMITS = RiskLimits()
