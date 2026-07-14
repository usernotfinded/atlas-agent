# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    market_data/__init__.py
# PURPOSE: Public surface of the market-data domain. Only the CSV provider is
#          exported: it is the one that is offline and deterministic, and therefore
#          the only one a backtest can be trusted to.
# DEPS:    market_data.base, market_data.csv_provider
# ==============================================================================

# --- IMPORTS ---
from atlas_agent.market_data.base import Bar, MarketDataProvider
from atlas_agent.market_data.csv_provider import CSVMarketDataProvider


# ==============================================================================
# PUBLIC API
# ==============================================================================

__all__ = ["Bar", "CSVMarketDataProvider", "MarketDataProvider"]

