# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    strategies/base.py
# PURPOSE: The strategy contract. Note the return type: an AIDecision — the SAME
#          type an LLM produces. A deterministic strategy and a model are
#          interchangeable to everything downstream, and both are equally subject
#          to the risk gates.
# DEPS:    ai.decision_schema (AIDecision), market_data.base (Bar)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from typing import Protocol

from atlas_agent.ai.decision_schema import AIDecision
from atlas_agent.market_data.base import Bar


# ==============================================================================
# STRATEGY CONTRACT
# ==============================================================================

class Strategy(Protocol):
    name: str

    # bars in, decision out. A strategy PROPOSES; it does not execute, does not touch a
    # broker, and cannot bypass risk. Keeping the signature this narrow is what enforces
    # that structurally rather than by convention.
    def decide(self, bars: list[Bar]) -> AIDecision:
        ...

