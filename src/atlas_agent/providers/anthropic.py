from __future__ import annotations

import os

from atlas_agent.providers.base import (
    ProviderConfigurationError,
    ProviderRequest,
    ProviderResponse,
)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key_env: str = "ANTHROPIC_API_KEY") -> None:
        self.api_key_env = api_key_env

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        if not os.getenv(self.api_key_env):
            raise ProviderConfigurationError(f"missing API key env var: {self.api_key_env}")
        raise ProviderConfigurationError(
            "Anthropic HTTP execution is not configured in this minimal install"
        )

