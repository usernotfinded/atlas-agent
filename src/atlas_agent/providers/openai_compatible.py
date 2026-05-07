from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass

from atlas_agent.providers.base import (
    ProviderConfigurationError,
    ProviderRequest,
    ProviderResponse,
)


@dataclass(frozen=True)
class OpenAICompatibleProvider:
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str = "https://api.openai.com/v1"
    name: str = "openai_compatible"

    @classmethod
    def from_env(cls, prefix: str = "OPENAI") -> OpenAICompatibleProvider:
        return cls(
            api_key_env=f"{prefix}_API_KEY",
            base_url=os.getenv(f"{prefix}_BASE_URL", "https://api.openai.com/v1"),
        )

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise ProviderConfigurationError(f"missing API key env var: {self.api_key_env}")
        body = json.dumps(
            {
                "model": request.model,
                "messages": [
                    {"role": "system", "content": request.system_prompt},
                    {"role": "user", "content": request.user_prompt},
                ],
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
            }
        ).encode("utf-8")
        http_request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(http_request, timeout=30) as response:
            raw = json.loads(response.read().decode("utf-8"))
        text = raw["choices"][0]["message"]["content"]
        return ProviderResponse(
            text=text,
            usage=raw.get("usage", {}),
            raw_response={"provider": self.name},
            finish_reason=raw["choices"][0].get("finish_reason", "stop"),
        )

