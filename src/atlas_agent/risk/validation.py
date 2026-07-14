# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    risk/validation.py
# PURPOSE: Legacy shape of a risk decision (allowed + reasons, nothing else).
#
# WARNING — NAME COLLISION: this `RiskDecision` is NOT the one in risk/models.py.
# They are two different types with the same name in the same package: the one in
# models.py is a rich pydantic model (status, violations, projections), this one is
# a frozen two-field dataclass used by old call sites. `risk/__init__.py` re-exports
# *the models.py one*, so importing from `atlas_agent.risk` and importing from
# `atlas_agent.risk.validation` yields two incompatible types. Worth consolidating.
#
# DEPS:    none (plain dataclass)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from dataclasses import dataclass


# ==============================================================================
# LEGACY DECISION SHAPE
# ==============================================================================

@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reasons: tuple[str, ...] = ()
