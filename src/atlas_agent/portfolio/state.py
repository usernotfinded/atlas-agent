# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    portfolio/state.py
# PURPOSE: The book. Cash, positions and today's counters — the state every risk
#          limit is evaluated against.
# DEPS:    portfolio.positions (Position)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from dataclasses import dataclass, field

from atlas_agent.portfolio.positions import Position


# ==============================================================================
# PORTFOLIO STATE
# ==============================================================================

@dataclass
class PortfolioState:
    cash: float = 10_000.0

    # Daily counters, reset by the caller at the session boundary. They back the
    # max_daily_loss and max_trades_per_day limits — which is why they live on the
    # state rather than being recomputed from a journal on every check.
    realized_pnl_today: float = 0.0
    trades_today: int = 0

    positions: dict[str, Position] = field(default_factory=dict)

    # Idempotency guard: an order id already seen is not applied twice. Without it, a
    # retried or replayed fill would double-count a position.
    seen_order_ids: set[str] = field(default_factory=set)

    # --- Derived values (the inputs to every risk limit) ---

    def equity(self, marks: dict[str, float] | None = None) -> float:
        """Net worth: cash plus the SIGNED value of every position."""
        # Falls back to average_price when a live mark is missing. That is a deliberate
        # conservatism: it values the position at cost, so an un-marked winner does not
        # inflate equity — and inflated equity would loosen every percentage-based limit.
        marks = marks or {}
        return self.cash + sum(
            position.market_value(marks.get(symbol, position.average_price))
            for symbol, position in self.positions.items()
        )

    def exposure(self, marks: dict[str, float] | None = None) -> float:
        """Gross exposure: the ABSOLUTE value of every position."""
        # abs(), unlike equity() above. A long and an offsetting short net to ~zero
        # equity but represent two full positions of market risk — summing them signed
        # would report a hedged book as carrying no exposure at all.
        marks = marks or {}
        return sum(
            abs(position.market_value(marks.get(symbol, position.average_price)))
            for symbol, position in self.positions.items()
        )

