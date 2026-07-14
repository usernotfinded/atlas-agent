# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    providers/null_provider.py
# PURPOSE: A provider that makes no model call and always says HOLD. The safe
#          default when no LLM is configured: the agent stays runnable end-to-end,
#          and the one thing it will never do is propose a trade.
# DEPS:    providers.base (the contract it implements)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import json

from atlas_agent.providers.base import BaseAIProvider, ProviderRequest, ProviderResponse
from atlas_agent.tools.spec import LLMResponse, ModelCapabilities, ToolDescription


# ==============================================================================
# NULL PROVIDER
# ==============================================================================

class NullProvider(BaseAIProvider):
    name = "null"

    def complete(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[ToolDescription],
        model: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        # Inputs explicitly discarded. This is not laziness — it is the contract: no
        # prompt content may influence the answer, because the answer is a constant.
        del system_prompt, messages, tools, model, temperature
        # action=hold, confidence=0.0, proposed_order=None. Every field is chosen so
        # that a downstream component treating this like a real decision still ends up
        # doing nothing: the confidence floor rejects it, and there is no order to route.
        payload = {
            "action": "hold",
            "symbol": "UNKNOWN",
            "confidence": 0.0,
            "time_horizon": "intraday",
            "reasoning_summary": "NullProvider deterministic hold.",
            "risk_notes": "No model call was made.",
            "proposed_order": None,
        }
        return LLMResponse(text=json.dumps(payload), tool_calls=[], is_final=True, raw=payload)

    def summarize(
        self,
        text: str,
        max_tokens: int,
    ) -> str:
        return super().summarize(text=text, max_tokens=max_tokens)

    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            context_window=8_192,
            supports_native_tools=False,
            supports_json_mode=False,
            supports_streaming=False,
            provider_name=self.name,
            model_name=None,
        )

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        payload = {
            "action": "hold",
            "symbol": request.metadata.get("symbol", "UNKNOWN"),
            "confidence": 0.0,
            "time_horizon": "intraday",
            "reasoning_summary": "NullProvider deterministic hold.",
            "risk_notes": "No model call was made.",
            "proposed_order": None,
        }
        return ProviderResponse(text=str(payload), parsed_json=payload)
