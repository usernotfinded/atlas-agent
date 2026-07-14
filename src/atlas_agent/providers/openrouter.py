# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    providers/openrouter.py
# PURPOSE: OpenRouter adapter. Thin, because OpenRouter speaks the OpenAI wire
#          format — all this adds is the right endpoint and an up-front key check.
# DEPS:    providers.openai_compatible (the shared implementation)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import os

from atlas_agent.providers.base import ProviderConfigurationError, ProviderRequest
from atlas_agent.providers.openai_compatible import OpenAICompatibleProvider


# ==============================================================================
# OPENROUTER PROVIDER
# ==============================================================================

class OpenRouterProvider(OpenAICompatibleProvider):
    def __init__(self) -> None:
        super().__init__(
            api_key_env="OPENROUTER_API_KEY",
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            name="openrouter",
            default_model=os.getenv("OPENROUTER_MODEL"),
        )

    def generate(self, request: ProviderRequest):
        # Checked here, BEFORE the request is built and sent. Without this the missing
        # key would surface as an opaque 401 from the vendor, which tells the operator
        # nothing about which env var they forgot to set.
        if not os.getenv(self.api_key_env):
            raise ProviderConfigurationError("missing API key env var: OPENROUTER_API_KEY")
        return super().generate(request)
