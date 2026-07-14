# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    risk/__init__.py
# PURPOSE: Public surface of the risk domain. Callers outside the package import
#          from here, not from the internal modules.
# DEPS:    risk.limits, risk.manager, risk.models
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from atlas_agent.risk.limits import RiskLimits
from atlas_agent.risk.manager import RiskManager

# Note: the RiskDecision re-exported here is the pydantic one from models.py, NOT
# the same-named dataclass in risk/validation.py. See the warning in validation.py.
from atlas_agent.risk.models import (
    OrderRiskInput,
    PortfolioSnapshot,
    RiskDecision,
    RiskPosition,
    RiskViolation,
)


# ==============================================================================
# PUBLIC API
# ==============================================================================

__all__ = [
    "OrderRiskInput",
    "PortfolioSnapshot",
    "RiskDecision",
    "RiskLimits",
    "RiskManager",
    "RiskPosition",
    "RiskViolation",
]
