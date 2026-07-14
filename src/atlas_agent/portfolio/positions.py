# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    portfolio/positions.py
# PURPOSE: A single holding. The atom the entire exposure calculation is built from.
# DEPS:    stdlib only (dataclasses)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from dataclasses import dataclass


# ==============================================================================
# POSITION
# ==============================================================================

@dataclass
class Position:
    symbol: str
    # SIGNED: negative means short. Every consumer must respect that — abs() where the
    # question is "how much exposure?", and the raw sign where it is "which way?".
    quantity: float = 0.0
    average_price: float = 0.0

    def market_value(self, price: float) -> float:
        # Signed too, and deliberately so. A short's market value is negative, which is
        # what makes a naive sum() over positions net out correctly in equity().
        # exposure() takes abs() precisely because it wants the opposite behaviour.
        return self.quantity * price

