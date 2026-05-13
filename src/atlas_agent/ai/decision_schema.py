from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


VALID_ACTIONS = {"buy", "sell", "hold", "close", "reduce", "increase"}
VALID_HORIZONS = {"intraday", "swing", "long"}
VALID_ORDER_TYPES = {"market", "limit"}


class DecisionSchemaError(ValueError):
    pass


@dataclass(frozen=True)
class ProposedOrder:
    side: str
    quantity: float
    order_type: str = "market"
    limit_price: float | None = None


@dataclass(frozen=True)
class AIDecision:
    action: str
    symbol: str
    confidence: float
    time_horizon: str
    reasoning_summary: str
    risk_notes: str
    proposed_order: ProposedOrder | None = None


def parse_decision(payload: str | dict[str, Any]) -> AIDecision:
    data = json.loads(payload) if isinstance(payload, str) else payload
    try:
        action = str(data["action"]).lower()
        symbol = str(data["symbol"]).upper()
        confidence = float(data["confidence"])
        time_horizon = str(data["time_horizon"]).lower()
    except (KeyError, TypeError, ValueError) as exc:
        raise DecisionSchemaError("AI decision missing required fields") from exc

    if action not in VALID_ACTIONS:
        raise DecisionSchemaError(f"invalid action: {action}")
    if time_horizon not in VALID_HORIZONS:
        raise DecisionSchemaError(f"invalid time horizon: {time_horizon}")
    if not 0 <= confidence <= 1:
        raise DecisionSchemaError("confidence must be between 0 and 1")

    proposed_order = _parse_order(data.get("proposed_order"))
    return AIDecision(
        action=action,
        symbol=symbol,
        confidence=confidence,
        time_horizon=time_horizon,
        reasoning_summary=str(data.get("reasoning_summary", "")),
        risk_notes=str(data.get("risk_notes", "")),
        proposed_order=proposed_order,
    )


def _is_positive_finite(value: float) -> bool:
    import math
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def _parse_order(payload: Any) -> ProposedOrder | None:
    if payload in (None, {}, "null"):
        return None
    try:
        side = str(payload["side"]).lower()
        raw_quantity = payload["quantity"]
        if isinstance(raw_quantity, bool):
            raise DecisionSchemaError("proposed_order.quantity must be a positive finite number")
        quantity = float(raw_quantity)
        order_type = str(payload.get("order_type", "market")).lower()
        limit_price = payload.get("limit_price")
    except DecisionSchemaError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise DecisionSchemaError("proposed_order is invalid") from exc
    if side not in {"buy", "sell"}:
        raise DecisionSchemaError("proposed_order.side must be buy or sell")
    if not _is_positive_finite(quantity):
        raise DecisionSchemaError("proposed_order.quantity must be a positive finite number")
    if order_type not in VALID_ORDER_TYPES:
        raise DecisionSchemaError("proposed_order.order_type is invalid")
    if limit_price is not None:
        if isinstance(limit_price, bool):
            raise DecisionSchemaError("proposed_order.limit_price must be a positive finite number")
        try:
            lp = float(limit_price)
        except (TypeError, ValueError):
            raise DecisionSchemaError("proposed_order.limit_price must be a number")
        if not _is_positive_finite(lp):
            raise DecisionSchemaError("proposed_order.limit_price must be a positive finite number")
    return ProposedOrder(
        side=side,
        quantity=quantity,
        order_type=order_type,
        limit_price=float(limit_price) if limit_price is not None else None,
    )

