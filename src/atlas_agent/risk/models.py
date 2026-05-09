from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class RiskPosition(BaseModel):
    symbol: str
    quantity: float
    average_price: float
    market_price: float
    notional: float
    side: Literal["long", "short", "flat"] = "flat"


class PortfolioSnapshot(BaseModel):
    cash: float
    equity: float
    total_exposure: float
    positions: list[RiskPosition] = Field(default_factory=list)
    realized_pnl_today: float = 0.0
    unrealized_pnl: float = 0.0
    trades_today: int = 0


class OrderRiskInput(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float
    price: float
    notional: float
    leverage: float = 1.0
    confidence: Optional[float] = None
    stop_loss: Optional[float] = None


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
    status: Literal["allowed", "blocked", "requires_approval"]
    reason: Optional[str] = None
    violations: list[RiskViolation] = Field(default_factory=list)
    classification: OrderClassification = "unknown"
    projected_quantity: float = 0.0
    projected_exposure: float = 0.0
    adjusted_order: Optional[dict[str, Any]] = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)
