from __future__ import annotations

from typing import Any

from atlas_agent.config import AtlasConfig
from atlas_agent.providers.anthropic import AnthropicProvider
from atlas_agent.providers.base import AIProvider, ProviderConfigurationError
from atlas_agent.providers.openai_compatible import OpenAICompatibleProvider
from atlas_agent.providers.runtime import resolve_runtime_provider


_OPENAI_COMPATIBLE_PROVIDERS = {
    "openai",
    "openrouter",
    "deepseek",
    "lmstudio",
    "openai-compatible",
    "custom",
}


def build_provider_from_runtime(runtime: dict[str, Any]) -> AIProvider:
    provider_id = str(runtime.get("provider") or "").strip()
    model = str(runtime.get("model") or "").strip()
    auth_method = str(runtime.get("auth_method") or "").strip()
    auth_header_type = str(runtime.get("auth_header_type") or "none").strip()
    base_url = str(runtime.get("base_url") or "").strip()
    api_key = str(runtime.get("api_key") or "")
    headers = runtime.get("headers") or {}
    errors = runtime.get("errors") or []

    if errors:
        raise ProviderConfigurationError("; ".join(str(error) for error in errors))

    if not provider_id:
        raise ProviderConfigurationError("No AI provider configured. Run `atlas model configure` or `atlas configure` before starting agentic workflows.")

    if provider_id == "google":
        if runtime.get("api_mode") != "openai_compatible":
            raise ProviderConfigurationError("Google native agent execution is not configured in this install.")
        if auth_method == "oauth_adc":
            raise ProviderConfigurationError("Google OAuth/ADC agent execution is not configured in this install.")
        provider_id = "openai-compatible"

    if provider_id in _OPENAI_COMPATIBLE_PROVIDERS:
        return OpenAICompatibleProvider(
            api_key_env=str(runtime.get("api_key_env_var_used") or "OPENAI_API_KEY"),
            base_url=base_url or "https://api.openai.com/v1",
            name=provider_id,
            default_model=model or None,
            api_key_override=api_key or None,
            auth_header_type=auth_header_type or "none",
            extra_headers=dict(headers),
        )

    if provider_id == "anthropic":
        return AnthropicProvider(
            api_key_env=str(runtime.get("api_key_env_var_used") or "ANTHROPIC_API_KEY"),
            default_model=model or None,
            api_key_override=api_key or None,
        )

    raise ProviderConfigurationError(
        f"Unknown or unconfigured AI provider: {provider_id}. Run `atlas model configure` or `atlas configure` before starting agentic workflows."
    )


def get_provider_from_runtime_config(
    config: AtlasConfig | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> AIProvider:
    runtime = resolve_runtime_provider(config, provider=provider, model=model)
    return build_provider_from_runtime(runtime)
