from __future__ import annotations

import os
from typing import Any

from atlas_agent.providers.base import AIProvider
from atlas_agent.providers.null_provider import NullProvider
from atlas_agent.providers.openai_compatible import OpenAICompatibleProvider


def get_provider_from_env() -> AIProvider:
    provider_name = os.getenv("AI_PROVIDER", "null").lower()
    
    if provider_name == "openai_compatible":
        return OpenAICompatibleProvider.from_env("OPENAI_COMPATIBLE")
    if provider_name == "openai":
        return OpenAICompatibleProvider.from_env("OPENAI")
    if provider_name == "anthropic":
        return AnthropicProvider.from_env()
    if provider_name == "openrouter":
        return OpenAICompatibleProvider.from_env("OPENROUTER")
    if provider_name == "deepseek":
        return OpenAICompatibleProvider.from_env("DEEPSEEK")
    
    return NullProvider()
