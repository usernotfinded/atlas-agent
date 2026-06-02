from __future__ import annotations

import os

from atlas_agent.providers.base import ProviderConfigurationError, ProviderRequest
from atlas_agent.providers.openai_compatible import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    def __init__(self) -> None:
        super().__init__(
            api_key_env="OPENROUTER_API_KEY",
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            name="openrouter",
            default_model=os.getenv("OPENROUTER_MODEL"),
        )

    def generate(self, request: ProviderRequest):
        if not os.getenv(self.api_key_env):
            raise ProviderConfigurationError("missing API key env var: OPENROUTER_API_KEY")
        return super().generate(request)
