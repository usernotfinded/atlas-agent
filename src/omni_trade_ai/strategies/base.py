from __future__ import annotations

from typing import Protocol

from omni_trade_ai.ai.decision_schema import AIDecision
from omni_trade_ai.market_data.base import Bar


class Strategy(Protocol):
    name: str

    def decide(self, bars: list[Bar]) -> AIDecision:
        ...

