from __future__ import annotations

import pytest

from atlas_agent.ai.decision_schema import DecisionSchemaError, parse_decision
from atlas_agent.ai.signal_parser import parse_and_validate_signal


def test_valid_decision_schema_parses() -> None:
    decision = parse_decision(
        {
            "action": "buy",
            "symbol": "btc-usd",
            "confidence": 0.8,
            "time_horizon": "swing",
            "reasoning_summary": "trend",
            "risk_notes": "small size",
            "proposed_order": {"side": "buy", "quantity": 1, "order_type": "market"},
        }
    )

    assert decision.action == "buy"
    assert decision.symbol == "BTC-USD"
    assert decision.proposed_order is not None


def test_invalid_ai_decision_is_rejected() -> None:
    with pytest.raises(DecisionSchemaError):
        parse_decision({"action": "moon", "symbol": "BTC-USD", "confidence": 0.9})


def test_low_confidence_decision_is_rejected_if_threshold_not_met() -> None:
    with pytest.raises(DecisionSchemaError, match="below risk threshold"):
        parse_and_validate_signal(
            {
                "action": "buy",
                "symbol": "BTC-USD",
                "confidence": 0.2,
                "time_horizon": "intraday",
                "reasoning_summary": "weak",
                "risk_notes": "weak",
            },
            minimum_confidence=0.55,
        )

