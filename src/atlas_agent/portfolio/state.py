from __future__ import annotations

from dataclasses import dataclass, field

from atlas_agent.portfolio.positions import Position


@dataclass
class PortfolioState:
    cash: float = 10_000.0
    realized_pnl_today: float = 0.0
    trades_today: int = 0
    positions: dict[str, Position] = field(default_factory=dict)
    seen_order_ids: set[str] = field(default_factory=set)

    def equity(self, marks: dict[str, float] | None = None) -> float:
        marks = marks or {}
        return self.cash + sum(
            position.market_value(marks.get(symbol, position.average_price))
            for symbol, position in self.positions.items()
        )

    def exposure(self, marks: dict[str, float] | None = None) -> float:
        marks = marks or {}
        return sum(
            abs(position.market_value(marks.get(symbol, position.average_price)))
            for symbol, position in self.positions.items()
        )

