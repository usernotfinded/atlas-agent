# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    strategies/breakout.py
# PURPOSE: Placeholder. NOT a breakout implementation.
# DEPS:    strategies.moving_average
#
# WARNING: This class computes NOTHING of its own. It subclasses
#          MovingAverageStrategy and overrides only the `name`, so selecting
#          "breakout" runs a moving-average crossover under a different label. No
#          breakout logic (range detection, level breach, volume confirmation)
#          exists anywhere in this file.
#
#          Any backtest or decision attributed to "breakout" is therefore a
#          moving-average result wearing the wrong name. Treat it as a stub.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from atlas_agent.strategies.moving_average import MovingAverageStrategy


# ==============================================================================
# BREAKOUT STRATEGY (STUB — see the warning above)
# ==============================================================================

class BreakoutStrategy(MovingAverageStrategy):
    name = "breakout"

