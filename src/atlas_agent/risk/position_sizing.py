from __future__ import annotations


def fixed_notional_quantity(notional: float, price: float) -> float:
    if notional <= 0:
        raise ValueError("notional must be positive")
    if price <= 0:
        raise ValueError("price must be positive")
    return notional / price

