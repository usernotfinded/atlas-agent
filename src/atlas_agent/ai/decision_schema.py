# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    ai/decision_schema.py
# PURPOSE: The border between the LLM and the trading system. Parses a model's
#          free-form JSON into a typed decision, and REJECTS anything malformed.
#          Everything past this file is trusted; nothing before it is.
# DEPS:    stdlib only (json, math)
#
# DESIGN:  An allowlist at every field. The model is an untrusted input source — it
#          hallucinates, it drifts, it can be steered by a poisoned prompt — so this
#          parser refuses rather than coerces. A decision that does not validate is
#          not a decision.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


# --- CONFIGURATIONS & CONSTANTS ---

# Closed sets, not free text. An action the system does not understand cannot be
# executed, so an LLM inventing "short_squeeze" is rejected rather than mishandled.
VALID_ACTIONS = {"buy", "sell", "hold", "close", "reduce", "increase"}
VALID_HORIZONS = {"intraday", "swing", "long"}
VALID_ORDER_TYPES = {"market", "limit"}


class DecisionSchemaError(ValueError):
    pass


# ==============================================================================
# DECISION MODELS
# ==============================================================================

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
    # Optional: an LLM may reason about a symbol without proposing a trade. `None` here
    # is the common case and the safe one.
    proposed_order: ProposedOrder | None = None


# ==============================================================================
# PARSING (the trust boundary)
# ==============================================================================

def parse_decision(payload: str | dict[str, Any]) -> AIDecision:
    """Parse an LLM payload into a typed decision, or raise.

    Raises:
        DecisionSchemaError: on any missing, malformed or out-of-range field.
    """
    # Raising, never defaulting. A missing `action` must not silently become "hold":
    # that would turn a broken model response into a valid-looking decision, and the
    # audit trail would record a choice nobody made.
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
    # Confidence feeds the minimum_confidence risk gate. An out-of-range value (a model
    # returning 95 instead of 0.95) would sail past that floor, so the range is bounded
    # here rather than trusted downstream.
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


# --- Order parsing ---

def _is_positive_finite(value: float) -> bool:
    # bool is excluded (True would pass as quantity 1) and NaN/inf are excluded (NaN
    # defeats every downstream limit comparison silently). This is the same guard the
    # order path applies — enforced here too, because a model is more likely to emit
    # nonsense than a strategy is.
    import math
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def _parse_order(payload: Any) -> ProposedOrder | None:
    # "null" the STRING is accepted alongside None: LLMs routinely emit it, and treating
    # it as a malformed order would reject an otherwise valid "no trade" answer.
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

