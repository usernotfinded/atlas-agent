# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    risk/position_sizing.py
# PURPOSE: Converts an amount of capital to commit into a quantity of instrument
#          to order. The single place where notional -> quantity happens.
# DEPS:    none (pure function)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import math


# ==============================================================================
# SIZING STRATEGIES
# ==============================================================================

def fixed_notional_quantity(notional: float, price: float) -> float:
    """
    Quantity to order in order to commit a fixed amount of capital at a given price.

    Args:
        notional: capital to commit, in currency.
        price: reference price of the instrument.

    Returns:
        Quantity of the instrument (may be fractional).

    Raises:
        ValueError: if notional or price are not strictly positive.
    """
    # Explicit guards rather than letting a divide-by-zero or a negative quantity
    # propagate: a bad size here becomes a bad order at the broker, so we fail
    # loudly as early as possible. Non-finite values are checked FIRST, because NaN
    # passes every ordinary comparison (`nan <= 0` is False) and would otherwise slip
    # through the positivity guard and return a NaN quantity — the exact hazard that
    # order_router and RiskManager reject at their own doors.
    if not math.isfinite(notional) or notional <= 0:
        raise ValueError("notional must be a positive finite number")
    if not math.isfinite(price) or price <= 0:
        raise ValueError("price must be a positive finite number")
    return notional / price
