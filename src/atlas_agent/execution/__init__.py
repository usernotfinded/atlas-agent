# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    execution/__init__.py
# PURPOSE: Public surface of the execution domain. Exposes only the value types;
#          the submit machinery is imported from its own modules by the few callers
#          that are allowed to place orders.
# DEPS:    execution.order
# ==============================================================================

# --- IMPORTS ---
from atlas_agent.execution.order import AccountSnapshot, Order, OrderResult


# ==============================================================================
# PUBLIC API
# ==============================================================================

__all__ = ["AccountSnapshot", "Order", "OrderResult"]
