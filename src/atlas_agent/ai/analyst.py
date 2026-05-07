from __future__ import annotations

from dataclasses import dataclass

from atlas_agent.ai.decision_schema import AIDecision, parse_decision
from atlas_agent.ai.prompt_builder import SYSTEM_PROMPT, build_market_prompt
from atlas_agent.providers.base import AIProvider, ProviderRequest


@dataclass(frozen=True)
class AIAnalyst:
    provider: AIProvider
    model: str = "default"

    def analyze(self, symbol: str) -> AIDecision:
        response = self.provider.generate(
            ProviderRequest(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=build_market_prompt(symbol),
                model=self.model,
                metadata={"symbol": symbol},
            )
        )
        return parse_decision(response.parsed_json or response.text)

