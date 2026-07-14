# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    execution/trade_executor.py
# PURPOSE: Backwards-compatible alias module. The implementation moved to
#          execution/order_router.py; this re-export keeps older imports working.
# DEPS:    execution.order_router
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from atlas_agent.execution.order_router import OrderRouter

__all__ = ["OrderRouter"]

