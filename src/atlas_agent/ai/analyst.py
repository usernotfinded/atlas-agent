# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    ai/analyst.py
# PURPOSE: Asks the model for a view on a symbol and returns a validated decision.
#          A thin seam: prompt in, typed decision out, with the parser as the guard.
# DEPS:    providers.base (any provider), ai.prompt_builder, ai.decision_schema
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from dataclasses import dataclass

from atlas_agent.ai.decision_schema import AIDecision, parse_decision
from atlas_agent.ai.prompt_builder import SYSTEM_PROMPT, build_market_prompt
from atlas_agent.providers.base import AIProvider, ProviderRequest


# ==============================================================================
# AI ANALYST
# ==============================================================================

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
        # The raw response NEVER escapes this method — it is parsed here or it raises.
        # `parsed_json or text` because providers differ in whether they hand back
        # structured output or a JSON string, and the parser accepts either.
        return parse_decision(response.parsed_json or response.text)

