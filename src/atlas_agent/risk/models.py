# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    risk/models.py
# PURPOSE: Data vocabulary of the risk domain. Defines what the RiskManager takes
#          in (proposed order + portfolio snapshot) and what it emits (decision +
#          violations). No business logic lives here.
# DEPS:    pydantic (validation + serialization into the audit log)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from typing import Any, Literal, Optional, List
from pydantic import BaseModel, Field


# ==============================================================================
# INPUT MODELS — the observed state of the world
# ==============================================================================

# --- Positions and in-flight orders ---

class RiskPosition(BaseModel):
    symbol: str
    quantity: float
    average_price: float
    market_price: float
    notional: float
    side: Literal["long", "short", "flat"] = "flat"


class PendingOrder(BaseModel):
    order_id: str
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float
    limit_price: Optional[float] = None
    estimated_price: Optional[float] = None
    status: Literal["pending", "open", "partially_filled", "cancelled", "filled", "rejected"]
    filled_quantity: float = 0.0

    @property
    def remaining_quantity(self) -> float:
        # A partial fill leaves only the remainder in flight, and that is what
        # weighs on projected risk — not the original order quantity. The clamp
        # to 0 guards against a broker reporting an over-fill.
        return max(0.0, self.quantity - self.filled_quantity)


# --- Portfolio snapshot ---

class PortfolioSnapshot(BaseModel):
    cash: float
    equity: float
    total_exposure: float
    positions: list[RiskPosition] = Field(default_factory=list)
    open_orders: list[PendingOrder] = Field(default_factory=list)
    realized_pnl_today: float = 0.0
    unrealized_pnl: float = 0.0
    trades_today: int = 0

    # Provenance of the snapshot: if the broker sync is degraded, whoever consumes
    # the decision must be able to tell it was made on possibly stale data.
    synced_at: Optional[str] = None
    sync_status: Literal["success", "partial", "failed"] = "success"
    sync_source: Optional[str] = None
    broker_id: Optional[str] = None


# --- Proposed order ---

class OrderRiskInput(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float
    price: float
    notional: float
    leverage: float = 1.0
    confidence: Optional[float] = None
    stop_loss: Optional[float] = None


# ==============================================================================
# OUTPUT MODELS — the outcome of an evaluation
# ==============================================================================

# Effect of the order on the existing position. This drives the limit exemption:
# an order that reduces risk must not be blocked by a size limit, otherwise the
# portfolio gets trapped precisely when it needs to de-risk.
OrderClassification = Literal[
    "opens_new_position",
    "increases_risk",
    "reduces_risk",
    "closes_position",
    "flips_position",
    "unknown"
]


class RiskViolation(BaseModel):
    rule: str
    message: str
    limit_value: Any
    actual_value: Any


class RiskDecision(BaseModel):
    allowed: bool

    # `allowed` and `status` are not redundant: in live mode an order can be
    # allowed=True with status="requires_approval", meaning it cleared risk but is
    # still waiting on a human before it may reach the broker.
    status: Literal["allowed", "blocked", "requires_approval"]
    reason: Optional[str] = None
    violations: list[RiskViolation] = Field(default_factory=list)
    classification: OrderClassification = "unknown"

    # Bare projections (current position only) vs "with_pending" ones (which also
    # count orders already in flight). Limits apply to the latter: ignoring pending
    # orders would let a caller breach any limit by slicing the order into tranches.
    projected_quantity: float = 0.0
    projected_exposure: float = 0.0
    projected_quantity_with_pending: float = 0.0
    projected_exposure_with_pending: float = 0.0

    adjusted_order: Optional[dict[str, Any]] = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)
