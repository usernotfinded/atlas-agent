from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from atlas_agent.providers.adapters import AnthropicAdapter
from atlas_agent.providers.base import (
    BaseAIProvider,
    ProviderConfigurationError,
    ProviderRequest,
    ProviderResponse,
)
from atlas_agent.tools.spec import LLMResponse, ModelCapabilities, ToolDescription


@dataclass(frozen=True)
class AnthropicProvider(BaseAIProvider):
    api_key_env: str = "ANTHROPIC_API_KEY"
    name: str = "anthropic"
    default_model: str | None = None

    @staticmethod
    def normalize_response(raw: dict[str, Any] | list[dict[str, Any]]) -> LLMResponse:
        return AnthropicAdapter.normalize(raw)

    def complete(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[ToolDescription],
        model: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        del system_prompt, messages, tools, model, temperature
        if not os.getenv(self.api_key_env):
            raise ProviderConfigurationError(f"missing API key env var: {self.api_key_env}")
        raise ProviderConfigurationError(
            "Anthropic HTTP execution is not configured in this minimal install"
        )

    def summarize(
        self,
        text: str,
        max_tokens: int,
    ) -> str:
        return super().summarize(text=text, max_tokens=max_tokens)

    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            context_window=200_000,
            supports_native_tools=True,
            supports_json_mode=False,
            supports_streaming=True,
            provider_name=self.name,
            model_name=self.default_model,
        )

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        response = self.complete(
            system_prompt=request.system_prompt,
            messages=[{"role": "user", "content": request.user_prompt}],
            tools=[],
            model=request.model,
            temperature=request.temperature,
        )
        return ProviderResponse(
            text=response.text or "",
            parsed_json=None,
            usage=response.usage.model_dump(exclude_none=True) if response.usage else {},
            raw_response=response.raw,
            finish_reason="stop" if response.is_final else "tool_calls",
        )
