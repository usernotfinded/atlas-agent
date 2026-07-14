# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    brokers/models.py
# PURPOSE: The normalised view of a broker account. Every venue reports positions,
#          orders and balances in its own dialect; these models are the one shape
#          the rest of the system reasons about, so adapters — not business logic —
#          absorb the differences.
# DEPS:    pydantic (models)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, List, Literal, Optional
from pydantic import BaseModel, Field


# ==============================================================================
# ACCOUNT CONTENTS
# ==============================================================================

class BrokerPosition(BaseModel):
    symbol: str
    quantity: float
    average_price: float
    market_price: Optional[float] = None
    # `side` is carried explicitly rather than inferred from the sign of `quantity`.
    # Venues disagree on whether a short is a negative quantity or a positive one with
    # a side flag, and letting each adapter state it removes the guesswork from the
    # code that later decides which way to trade to close.
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


# ==============================================================================
# SYNC RESULT
# ==============================================================================

class BrokerSyncResult(BaseModel):
    # "partial" is a first-class outcome, not a rounding error. Some endpoints can fail
    # while others succeed, and live_sync_validation.py decides which of those gaps are
    # survivable — a boolean here would throw away the information it needs.
    status: Literal["success", "partial", "failed"]

    # Optional even on "success": an empty account is not the same as an unsynced one,
    # and validate_live_sync() treats `account is None` as a critical failure regardless
    # of what `status` claims.
    account: Optional[BrokerAccountState] = None
    positions: List[BrokerPosition] = Field(default_factory=list)
    open_orders: List[BrokerOrder] = Field(default_factory=list)
    balances: List[BrokerBalance] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)

    # Carries the structured broker_errors list that validate_live_sync() parses to
    # decide whether a live submit may proceed. Despite the name, this is not merely
    # informational — it is load-bearing.
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    synced_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
