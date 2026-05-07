from __future__ import annotations

from atlas_agent.ai.decision_schema import AIDecision, DecisionSchemaError, parse_decision


def parse_and_validate_signal(
    payload: str | dict[str, object],
    *,
    minimum_confidence: float,
) -> AIDecision:
    decision = parse_decision(payload)
    if decision.action != "hold" and decision.confidence < minimum_confidence:
        raise DecisionSchemaError("AI decision confidence is below risk threshold")
    return decision

