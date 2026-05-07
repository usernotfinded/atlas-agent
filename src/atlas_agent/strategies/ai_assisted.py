from __future__ import annotations

from dataclasses import dataclass

from atlas_agent.ai.committee import AICommittee
from atlas_agent.ai.decision_schema import AIDecision
from atlas_agent.market_data.base import Bar


@dataclass(frozen=True)
class AIAssistedStrategy:
    committee: AICommittee
    name: str = "ai_assisted"

    def decide(self, bars: list[Bar]) -> AIDecision:
        if not bars:
            raise ValueError("bars are required")
        return self.committee.decide(bars[-1].symbol)

