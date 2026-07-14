# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    market_data/base.py
# PURPOSE: The OHLCV bar and the contract for anything that supplies them. One
#          shape for CSV files, yfinance and any future feed, so strategies and the
#          backtest engine never learn where their data came from.
# DEPS:    stdlib only (dataclasses, typing.Protocol)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


# ==============================================================================
# BAR
# ==============================================================================

# Frozen: a bar is a historical fact. Backtests replay the same bars repeatedly, and
# a mutable one could be modified by a strategy and silently poison every later run.
@dataclass(frozen=True)
class Bar:
    date: date
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float


# ==============================================================================
# PROVIDER CONTRACT
# ==============================================================================

class MarketDataProvider(Protocol):
    def load_bars(self, symbol: str) -> list[Bar]:
        ...

