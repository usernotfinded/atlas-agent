# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    safety/policy.py
# PURPOSE: The project's non-negotiable safety invariants, stated in one place and
#          in plain English. Documentation with a stable import path: surfaced in
#          the CLI and asserted against by the trust checkers, so the promises made
#          to users and the promises made in code cannot silently diverge.
# DEPS:    none
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations


# --- CONFIGURATIONS & CONSTANTS ---

HARD_RULES = (
    "No API keys in git.",
    "No live trading by default.",
    "No AI direct-to-broker execution.",
    "RiskManager is mandatory before broker execution.",
    "Kill switch overrides every order path.",
    "Manual approval is default for live mode.",
)

