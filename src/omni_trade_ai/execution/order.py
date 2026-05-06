from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


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
        return self.quantity * (self.limit_price or 0.0)

    def with_price(self, price: float) -> Order:
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


@dataclass(frozen=True)
class OrderResult:
    accepted: bool
    filled: bool
    order_id: str
    status: str
    message: str
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class AccountSnapshot:
    cash: float
    equity: float
    buying_power: float
    mode: str

