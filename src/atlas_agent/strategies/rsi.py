# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    strategies/rsi.py
# PURPOSE: Placeholder. NOT an RSI implementation.
# DEPS:    strategies.moving_average
#
# WARNING: This class computes NOTHING of its own. It subclasses
#          MovingAverageStrategy and overrides only the `name`, so selecting "rsi"
#          runs a moving-average crossover under a different label. No relative
#          strength index is calculated anywhere in this file.
#
#          Any backtest or decision attributed to "rsi" is therefore a moving-average
#          result wearing the wrong name. Treat it as a stub, not a strategy.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from atlas_agent.strategies.moving_average import MovingAverageStrategy


# ==============================================================================
# RSI STRATEGY (STUB — see the warning above)
# ==============================================================================

class RSIStrategy(MovingAverageStrategy):
    name = "rsi"

