from __future__ import annotations

import os
from typing import Any

from atlas_agent.providers.base import AIProvider
from atlas_agent.providers.null_provider import NullProvider
from atlas_agent.providers.openai_compatible import OpenAICompatibleProvider
from atlas_agent.providers.anthropic import AnthropicProvider


def get_provider_from_env(allow_null: bool = False) -> AIProvider:
    provider_name = os.getenv("AI_PROVIDER", "null").lower()
    
    if provider_name in ("openai_compatible", "custom"):
        return OpenAICompatibleProvider.from_env("OPENAI_COMPATIBLE")
    if provider_name == "openai":
        return OpenAICompatibleProvider.from_env("OPENAI")
    if provider_name == "anthropic":
        return AnthropicProvider.from_env()
    if provider_name == "openrouter":
        return OpenAICompatibleProvider.from_env("OPENROUTER")
    if provider_name == "deepseek":
        return OpenAICompatibleProvider.from_env("DEEPSEEK")
    if provider_name == "lmstudio":
        return OpenAICompatibleProvider.from_env("LMSTUDIO")
    
    if provider_name == "null":
        if allow_null:
            return NullProvider()
        raise ValueError("No AI provider configured. Run `atlas model configure` or `atlas configure` before starting agentic workflows.")
    
    # Fallback for unknown provider if not handled above
    if allow_null:
        return NullProvider()
        
    raise ValueError(f"Unknown or unconfigured AI provider: {provider_name}. Run `atlas model configure` or `atlas configure` before starting agentic workflows.")
