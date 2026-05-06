from __future__ import annotations

from dataclasses import dataclass

from omni_trade_ai.ai.committee import AICommittee
from omni_trade_ai.ai.decision_schema import AIDecision
from omni_trade_ai.market_data.base import Bar


@dataclass(frozen=True)
class AIAssistedStrategy:
    committee: AICommittee
    name: str = "ai_assisted"

    def decide(self, bars: list[Bar]) -> AIDecision:
        if not bars:
            raise ValueError("bars are required")
        return self.committee.decide(bars[-1].symbol)

