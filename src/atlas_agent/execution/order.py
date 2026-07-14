# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    execution/order.py
# PURPOSE: The core value types of the order path — the order itself and the
#          results a broker hands back. All frozen: an order that could be mutated
#          after it passed risk checks would make those checks meaningless.
# DEPS:    stdlib only (dataclasses, math, uuid)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


# ==============================================================================
# ORDER
# ==============================================================================

@dataclass(frozen=True)
class Order:
    symbol: str
    side: str
    quantity: float
    order_type: str = "market"
    limit_price: float | None = None
    confidence: float = 1.0
    stop_loss: float | None = None
    leverage: float = 1.0
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: str = "strategy"

    @property
    def notional(self) -> float:
        """Order value. RAISES when it cannot be known — it never guesses.

        Returns:
            quantity * limit_price.

        Raises:
            ValueError: if either input is missing, non-finite or non-positive.
        """
        # This value feeds every risk limit in the system, so the guards are
        # exhaustive on purpose. Each clause blocks a way a bad notional could slip
        # through and silently defeat a cap:
        #   - None          → a market order with no reference price. Returning 0 here
        #                     would sail past every notional limit as "free".
        #   - bool          → Python says isinstance(True, int), and True * price
        #                     would evaluate to price. Excluded explicitly.
        #   - not finite    → NaN defeats every comparison: NaN > max_notional is
        #                     False, so a NaN notional passes ALL limit checks.
        #   - <= 0          → a negative notional would likewise pass every ceiling.
        # Raising beats returning a sentinel: the caller must not be able to ignore it.
        if self.limit_price is None or isinstance(self.limit_price, bool) or not isinstance(self.limit_price, (int, float)) or not math.isfinite(self.limit_price) or self.limit_price <= 0:
            raise ValueError("Cannot evaluate notional for market order without reference price")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, (int, float)) or not math.isfinite(self.quantity) or self.quantity <= 0:
            raise ValueError("order quantity must be a positive finite number")
        return self.quantity * self.limit_price

    def with_price(self, price: float) -> Order:
        """Attach a reference price, without overwriting one already set."""
        # `price if self.limit_price is None else self.limit_price` — an existing limit
        # price WINS. This method exists to give a market order a reference price for
        # risk evaluation; it must never quietly reprice a limit order the strategy set
        # deliberately.
        # `id` and `created_at` are carried over so the order stays the same order
        # through the pipeline and remains traceable in the audit log.
        return Order(
            symbol=self.symbol,
            side=self.side,
            quantity=self.quantity,
            order_type=self.order_type,
            limit_price=price if self.limit_price is None else self.limit_price,
            confidence=self.confidence,
            stop_loss=self.stop_loss,
            leverage=self.leverage,
            id=self.id,
            created_at=self.created_at,
            source=self.source,
        )


# ==============================================================================
# BROKER RESULTS
# ==============================================================================

@dataclass(frozen=True)
class OrderResult:
    # `accepted` and `filled` are independent, and conflating them is a classic way to
    # lose money: a broker can accept an order that never fills (a resting limit), and
    # accepted=True says nothing about whether exposure actually changed.
    accepted: bool
    filled: bool
    order_id: str
    status: str
    message: str
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class FlattenResult:
    accepted: bool
    status: str
    message: str
    strategy: str
    bps: int
    # attempted / closed / failed are reported separately because a partial flatten is
    # the dangerous case: closed < attempted means positions are STILL OPEN, and a
    # single boolean would hide exactly the fact the operator needs to act on.
    attempted: int
    closed: int
    failed: int
    order_results: tuple[OrderResult, ...] = ()
    failed_symbols: tuple[str, ...] = ()


@dataclass(frozen=True)
class AccountSnapshot:
    cash: float
    equity: float
    buying_power: float
    mode: str
