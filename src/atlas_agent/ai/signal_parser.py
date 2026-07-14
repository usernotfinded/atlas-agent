# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    ai/signal_parser.py
# PURPOSE: Parses an LLM decision AND enforces the confidence floor on it. The
#          schema check answers "is this well-formed?"; this adds "is it convinced
#          enough to act on?".
# DEPS:    ai.decision_schema (the parser it wraps)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from atlas_agent.ai.decision_schema import AIDecision, DecisionSchemaError, parse_decision


# ==============================================================================
# SIGNAL VALIDATION
# ==============================================================================

def parse_and_validate_signal(
    payload: str | dict[str, object],
    *,
    minimum_confidence: float,
) -> AIDecision:
    decision = parse_decision(payload)
    # "hold" is exempt from the confidence floor, and that asymmetry is the point:
    # doing nothing needs no conviction. Only a decision that would MOVE the portfolio
    # has to clear the bar — a low-confidence hold is still a perfectly good hold.
    if decision.action != "hold" and decision.confidence < minimum_confidence:
        raise DecisionSchemaError("AI decision confidence is below risk threshold")
    return decision

