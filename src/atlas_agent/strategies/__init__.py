# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    strategies/__init__.py
# PURPOSE: Public surface of the strategies domain. Only the moving-average strategy
#          is complete; breakout.py and rsi.py are stubs and are not exported.
# DEPS:    strategies.moving_average
# ==============================================================================

# --- IMPORTS ---
from atlas_agent.strategies.moving_average import MovingAverageStrategy


# ==============================================================================
# PUBLIC API
# ==============================================================================

__all__ = ["MovingAverageStrategy"]

