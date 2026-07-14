# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    providers/factory.py
# PURPOSE: Turns resolved runtime config into a concrete AIProvider. The one place
#          that decides which vendor the agent talks to — and the place that decides
#          when to talk to nobody at all.
# DEPS:    providers.runtime (resolution), the concrete adapters, providers.base
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from typing import Any

from atlas_agent.config import AtlasConfig
from atlas_agent.providers.anthropic import AnthropicProvider
from atlas_agent.providers.base import AIProvider, ProviderConfigurationError
from atlas_agent.providers.null_provider import NullProvider
from atlas_agent.providers.openai_compatible import OpenAICompatibleProvider
from atlas_agent.providers.runtime import resolve_runtime_provider


# --- CONFIGURATIONS & CONSTANTS ---

# All of these speak the OpenAI wire format, so one adapter serves them all. The list
# is what makes adding an OpenAI-compatible vendor a one-line change.
_OPENAI_COMPATIBLE_PROVIDERS = {
    "openai",
    "openrouter",
    "deepseek",
    "lmstudio",
    "openai-compatible",
    "custom",
}


# ==============================================================================
# PROVIDER CONSTRUCTION
# ==============================================================================

def build_provider_from_runtime(runtime: dict[str, Any]) -> AIProvider:
    # An allowlist with no default branch: an unrecognised provider id RAISES at the
    # bottom rather than falling back to something. "I don't know this vendor" must not
    # resolve into a working model call against an unreviewed endpoint.
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

    if provider_id == "null":
        return NullProvider()

    raise ProviderConfigurationError(
        f"Unknown or unconfigured AI provider: {provider_id}. Run `atlas model configure` or `atlas configure` before starting agentic workflows."
    )


def get_provider_from_runtime_config(
    config: AtlasConfig | None = None,
    provider: str | None = None,
    model: str | None = None,
    mode: str | None = None,
) -> AIProvider:
    """Resolve an AI provider from runtime configuration.

    Args:
        config: Effective Atlas configuration.
        provider: Optional explicit provider ID override.
        model: Optional explicit model ID override.
        mode: Effective trading mode ("paper", "live", etc.). When mode is
            "paper" and the configured provider is missing credentials,
            the offline NullProvider is used instead of attempting a network
            call. Live mode never falls back to NullProvider.
    """
    import logging

    runtime = resolve_runtime_provider(config, provider=provider, model=model)

    # The paper-only fallback. Missing credentials in PAPER degrade to the offline
    # NullProvider (warn and carry on) — a beginner exploring the tool should not hit a
    # wall before they have an API key.
    #
    # There is deliberately NO equivalent branch for live. In live mode, missing
    # credentials fall through to build_provider_from_runtime() and RAISE. Falling back
    # to a "hold forever" provider on a live account would be a silent, invisible
    # failure — the agent would appear healthy while doing nothing at all.
    if mode == "paper":
        provider_id = str(runtime.get("provider") or "").strip()
        if provider_id == "null":
            return NullProvider()

        credential_source = str(runtime.get("credential_source") or "").strip()
        if credential_source == "missing":
            logging.warning(
                "Paper mode: AI provider '%s' credentials are missing. "
                "Falling back to the offline NullProvider (no network, no API key). "
                "Set provider credentials or pass --offline explicitly to silence this warning.",
                provider_id or "default",
            )
            return NullProvider()

    return build_provider_from_runtime(runtime)
