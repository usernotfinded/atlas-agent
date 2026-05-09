from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, List, Literal, Optional
from pydantic import BaseModel, Field


class BrokerPosition(BaseModel):
    symbol: str
    quantity: float
    average_price: float
    market_price: Optional[float] = None
    side: Literal["long", "short", "flat"]


class BrokerOrder(BaseModel):
    order_id: str
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float
    limit_price: Optional[float] = None
    status: Literal["pending", "open", "partially_filled", "cancelled", "filled", "rejected"]
    filled_quantity: float = 0.0
    created_at: Optional[str] = None


class BrokerBalance(BaseModel):
    asset: str
    free: float
    locked: float
    total: float


class BrokerAccountState(BaseModel):
    account_id: str
    currency: str = "USD"
    cash: float
    equity: float
    buying_power: Optional[float] = None
    is_live: bool = False


class BrokerSyncResult(BaseModel):
    status: Literal["success", "partial", "failed"]
    account: Optional[BrokerAccountState] = None
    positions: List[BrokerPosition] = Field(default_factory=list)
    open_orders: List[BrokerOrder] = Field(default_factory=list)
    balances: List[BrokerBalance] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    synced_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
