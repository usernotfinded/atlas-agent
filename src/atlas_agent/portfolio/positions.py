from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Position:
    symbol: str
    quantity: float = 0.0
    average_price: float = 0.0

    def market_value(self, price: float) -> float:
        return self.quantity * price

