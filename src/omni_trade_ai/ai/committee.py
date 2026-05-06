from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from omni_trade_ai.ai.analyst import AIAnalyst
from omni_trade_ai.ai.decision_schema import AIDecision


@dataclass(frozen=True)
class AICommittee:
    analysts: tuple[AIAnalyst, ...]

    def decide(self, symbol: str) -> AIDecision:
        if not self.analysts:
            raise ValueError("AICommittee requires at least one analyst")
        decisions = [analyst.analyze(symbol) for analyst in self.analysts]
        action_counts = Counter(decision.action for decision in decisions)
        winning_action = action_counts.most_common(1)[0][0]
        finalists = [item for item in decisions if item.action == winning_action]
        return max(finalists, key=lambda item: item.confidence)

