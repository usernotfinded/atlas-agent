# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    market_data/yfinance_provider.py
# PURPOSE: Placeholder for a yfinance-backed feed. Unimplemented on purpose: it
#          raises rather than returning empty bars, because a backtest that silently
#          ran on no data would report a clean, meaningless result.
# DEPS:    market_data.base (Bar)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from atlas_agent.market_data.base import Bar


# ==============================================================================
# YFINANCE PROVIDER (not implemented)
# ==============================================================================

class YFinanceProvider:
    def load_bars(self, symbol: str) -> list[Bar]:
        raise RuntimeError(
            "yfinance support is optional; install and configure it before use"
        )

