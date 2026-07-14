# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    risk/limits.py
# PURPOSE: Configurable risk thresholds and their canonical defaults. This is the
#          "constitution" the RiskManager enforces: it declares what is allowed,
#          not how it is checked.
# DEPS:    pydantic (validation of limits loaded from config/env)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from typing import Optional, Set
from pydantic import BaseModel, Field


# --- CONFIGURATIONS & CONSTANTS ---

# Canonical defaults for RiskLimits.
# These are the single source of truth for the risk model.
# Env/example values in .env.example may use more conservative absolute
# numbers for illustration; the model defaults below are authoritative.
DEFAULT_MAX_POSITION_NOTIONAL = 1000.0
DEFAULT_MAX_SINGLE_TRADE_NOTIONAL = 500.0
DEFAULT_MAX_DAILY_LOSS_PCT = 0.02
DEFAULT_MINIMUM_CONFIDENCE = 0.6
DEFAULT_MAX_OPEN_POSITIONS = 10


# ==============================================================================
# RISK LIMITS MODEL
# ==============================================================================

class RiskLimits(BaseModel):
    # --- Size limits ---
    max_position_notional: float = Field(default=DEFAULT_MAX_POSITION_NOTIONAL, description="Max notional value for a single position")
    max_symbol_exposure_pct: float = Field(default=0.25, description="Max exposure to a single symbol as % of equity")
    max_portfolio_exposure_pct: float = Field(default=1.0, description="Max total portfolio exposure as % of equity")
    max_single_trade_notional: float = Field(default=DEFAULT_MAX_SINGLE_TRADE_NOTIONAL, description="Max notional value for a single trade")
    max_daily_loss_pct: float = Field(default=DEFAULT_MAX_DAILY_LOSS_PCT, description="Max daily loss as % of equity")
    max_open_positions: int = Field(default=DEFAULT_MAX_OPEN_POSITIONS, description="Max number of concurrent open positions")

    # --- Tradable universe ---
    # `allowed_symbols=None` means "everything" and is NOT the same as an empty set,
    # which would mean "nothing". Collapsing that distinction would open trading on
    # any symbol whenever a config is malformed.
    allowed_symbols: Optional[Set[str]] = Field(default=None, description="Set of symbols allowed for trading. None means all.")
    blocked_symbols: Set[str] = Field(default_factory=set, description="Set of symbols explicitly blocked.")

    # --- Live/paper gate ---
    # Two switches on purpose: `paper_only` must be False *and* `live_trading_enabled`
    # must be True for a live order to pass. A single flag would be far too easy to
    # flip by accident in a config file.
    paper_only: bool = Field(default=True, description="If true, only paper trading is allowed.")
    live_trading_enabled: bool = Field(default=False, description="Explicit flag to enable live trading.")

    # --- Execution policy ---
    minimum_confidence: float = Field(default=DEFAULT_MINIMUM_CONFIDENCE, description="Minimum model confidence required for execution.")
    require_stop_loss_live: bool = Field(default=True, description="Require a stop loss for live orders.")
    allow_shorting: bool = Field(default=False, description="Allow opening or flipping to short positions.")


# Shared default. Consumers normally build their own RiskLimits from config; this
# exists as a safe fallback (paper-only, shorting off).
DEFAULT_RISK_LIMITS = RiskLimits()
