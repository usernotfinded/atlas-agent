# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    strategies/__init__.py
# PURPOSE: Public surface of the strategies domain. Each strategy takes bars and
#          returns an AIDecision — the same type an LLM produces — so all of them
#          are equally subject to the risk gates downstream.
# DEPS:    strategies.moving_average, strategies.rsi, strategies.breakout
# ==============================================================================

# --- IMPORTS ---
from atlas_agent.strategies.breakout import BreakoutStrategy
from atlas_agent.strategies.moving_average import MovingAverageStrategy
from atlas_agent.strategies.rsi import RSIStrategy


# ==============================================================================
# PUBLIC API
# ==============================================================================

__all__ = ["BreakoutStrategy", "MovingAverageStrategy", "RSIStrategy"]

