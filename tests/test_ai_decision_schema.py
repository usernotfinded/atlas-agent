# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_ai_decision_schema.py
# PURPOSE: Verifies ai decision schema behavior and regression expectations.
# DEPS:    pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import pytest

from atlas_agent.ai.decision_schema import DecisionSchemaError, parse_decision
from atlas_agent.ai.signal_parser import parse_and_validate_signal


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_valid_decision_schema_parses() -> None:
    decision = parse_decision(
        {
            "action": "buy",
            "symbol": "test-symbol",
            "confidence": 0.8,
            "time_horizon": "swing",
            "reasoning_summary": "trend",
            "risk_notes": "small size",
            "proposed_order": {"side": "buy", "quantity": 1, "order_type": "market"},
        }
    )

    assert decision.action == "buy"
    assert decision.symbol == "TEST-SYMBOL"
    assert decision.proposed_order is not None


def test_invalid_ai_decision_is_rejected() -> None:
    with pytest.raises(DecisionSchemaError):
        parse_decision({"action": "moon", "symbol": "TEST-SYMBOL", "confidence": 0.9})


def test_low_confidence_decision_is_rejected_if_threshold_not_met() -> None:
    with pytest.raises(DecisionSchemaError, match="below risk threshold"):
        parse_and_validate_signal(
            {
                "action": "buy",
                "symbol": "TEST-SYMBOL",
                "confidence": 0.2,
                "time_horizon": "intraday",
                "reasoning_summary": "weak",
                "risk_notes": "weak",
            },
            minimum_confidence=0.55,
        )


@pytest.mark.parametrize("bad_quantity", [float("nan"), float("inf"), float("-inf"), 0, -1])
def test_decision_schema_rejects_invalid_quantity(bad_quantity) -> None:
    with pytest.raises(DecisionSchemaError, match="quantity must be a positive finite number"):
        parse_decision(
            {
                "action": "buy",
                "symbol": "TEST-SYMBOL",
                "confidence": 0.8,
                "time_horizon": "swing",
                "reasoning_summary": "trend",
                "risk_notes": "small size",
                "proposed_order": {"side": "buy", "quantity": bad_quantity, "order_type": "market"},
            }
        )


@pytest.mark.parametrize("bad_limit_price", [float("nan"), float("inf"), float("-inf"), 0, -1])
def test_decision_schema_rejects_invalid_limit_price(bad_limit_price) -> None:
    with pytest.raises(DecisionSchemaError, match="limit_price must be a positive finite number"):
        parse_decision(
            {
                "action": "buy",
                "symbol": "TEST-SYMBOL",
                "confidence": 0.8,
                "time_horizon": "swing",
                "reasoning_summary": "trend",
                "risk_notes": "small size",
                "proposed_order": {"side": "buy", "quantity": 1, "order_type": "limit", "limit_price": bad_limit_price},
            }
        )


def test_decision_schema_accepts_valid_positive_finite_numbers() -> None:
    decision = parse_decision(
        {
            "action": "buy",
            "symbol": "test-symbol",
            "confidence": 0.8,
            "time_horizon": "swing",
            "reasoning_summary": "trend",
            "risk_notes": "small size",
            "proposed_order": {"side": "buy", "quantity": 1.5, "order_type": "limit", "limit_price": 150.0},
        }
    )
    assert decision.proposed_order is not None
    assert decision.proposed_order.quantity == 1.5
    assert decision.proposed_order.limit_price == 150.0


@pytest.mark.parametrize("bad_quantity", [True, False])
def test_decision_schema_rejects_boolean_quantity(bad_quantity) -> None:
    with pytest.raises(DecisionSchemaError, match="quantity must be a positive finite number"):
        parse_decision(
            {
                "action": "buy",
                "symbol": "TEST-SYMBOL",
                "confidence": 0.8,
                "time_horizon": "swing",
                "reasoning_summary": "trend",
                "risk_notes": "small size",
                "proposed_order": {"side": "buy", "quantity": bad_quantity, "order_type": "market"},
            }
        )


@pytest.mark.parametrize("bad_limit_price", [True, False])
def test_decision_schema_rejects_boolean_limit_price(bad_limit_price) -> None:
    with pytest.raises(DecisionSchemaError, match="limit_price must be a positive finite number"):
        parse_decision(
            {
                "action": "buy",
                "symbol": "TEST-SYMBOL",
                "confidence": 0.8,
                "time_horizon": "swing",
                "reasoning_summary": "trend",
                "risk_notes": "small size",
                "proposed_order": {"side": "buy", "quantity": 1, "order_type": "limit", "limit_price": bad_limit_price},
            }
        )
