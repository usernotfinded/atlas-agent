from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any

from atlas_agent.providers.adapters import OpenAICompatibleAdapter
from atlas_agent.providers.base import (
    BaseAIProvider,
    ProviderConfigurationError,
    ProviderRequest,
    ProviderResponse,
)
from atlas_agent.tools.spec import LLMResponse, ModelCapabilities, ToolDescription


@dataclass(frozen=True)
class OpenAICompatibleProvider(BaseAIProvider):
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str = "https://api.openai.com/v1"
    name: str = "openai_compatible"
    default_model: str | None = None
    api_key_override: str | None = None
    auth_header_type: str = "bearer"
    extra_headers: dict[str, str] | None = None

    @classmethod
    def from_env(cls, prefix: str = "OPENAI") -> OpenAICompatibleProvider:
        return cls(
            api_key_env=f"{prefix}_API_KEY",
            base_url=os.getenv(f"{prefix}_BASE_URL", "https://api.openai.com/v1"),
            default_model=os.getenv(f"{prefix}_MODEL"),
        )

    @staticmethod
    def normalize_response(raw: dict[str, Any]) -> LLMResponse:
        return OpenAICompatibleAdapter.normalize(raw)

    def complete(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[ToolDescription],
        model: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        api_key = self.api_key_override
        if api_key is None:
            api_key = os.getenv(self.api_key_env)

        if self.auth_header_type != "none" and not api_key:
            raise ProviderConfigurationError(f"missing API key env var: {self.api_key_env}")

        selected_model = model or self.default_model
        if not selected_model:
            raise ProviderConfigurationError(
                "model must be provided explicitly or configured as default_model"
            )

        payload_messages = [{"role": "system", "content": system_prompt}] + list(messages)
        body: dict[str, Any] = {
            "model": selected_model,
            "messages": payload_messages,
            "temperature": temperature,
        }
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.schema_dict,
                    },
                }
                for tool in tools
            ]
            body["tool_choice"] = "auto"

        headers = {
            "Content-Type": "application/json",
        }
        if self.extra_headers:
            headers.update(self.extra_headers)
        if self.auth_header_type == "bearer" and api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        elif self.auth_header_type == "x-goog-api-key" and api_key:
            headers["x-goog-api-key"] = api_key
        elif self.auth_header_type == "oauth_bearer" and api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        request_body = json.dumps(body).encode("utf-8")
        http_request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=request_body,
            headers=headers,
            method="POST",
        )

        with urllib.request.urlopen(http_request, timeout=30) as response:
            raw = json.loads(response.read().decode("utf-8"))
        return self.normalize_response(raw)

    def summarize(
        self,
        text: str,
        max_tokens: int,
    ) -> str:
        return super().summarize(text=text, max_tokens=max_tokens)

    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            context_window=128_000,
            supports_native_tools=True,
            supports_json_mode=True,
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
        parsed_json = None
        if response.text:
            try:
                loaded = json.loads(response.text)
                if isinstance(loaded, dict):
                    parsed_json = loaded
            except json.JSONDecodeError:
                parsed_json = None

        return ProviderResponse(
            text=response.text or "",
            parsed_json=parsed_json,
            usage=response.usage.model_dump(exclude_none=True) if response.usage else {},
            raw_response=response.raw,
            finish_reason="stop" if response.is_final else "tool_calls",
        )
