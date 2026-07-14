# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    ai/__init__.py
# PURPOSE: Public surface of the AI domain. Exports the validated decision types
#          and the parser — never a raw provider response, so no caller can bypass
#          the schema check that stands between the model and the order path.
# DEPS:    ai.decision_schema
# ==============================================================================

# --- IMPORTS ---
from atlas_agent.ai.decision_schema import AIDecision, ProposedOrder, parse_decision


# ==============================================================================
# PUBLIC API
# ==============================================================================

__all__ = ["AIDecision", "ProposedOrder", "parse_decision"]

