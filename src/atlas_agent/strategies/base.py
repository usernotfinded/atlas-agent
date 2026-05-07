from __future__ import annotations

from typing import Protocol

from atlas_agent.ai.decision_schema import AIDecision
from atlas_agent.market_data.base import Bar


class Strategy(Protocol):
    name: str

    def decide(self, bars: list[Bar]) -> AIDecision:
        ...

