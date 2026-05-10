from __future__ import annotations

import os
from typing import Any

from atlas_agent.config.schema import AtlasConfig
from atlas_agent.config.secrets import get_secret
from atlas_agent.providers.catalog import (
    get_provider_profile,
    normalize_provider_id,
    default_model_for_provider,
    ProviderProfile,
)


def _resolve_api_key(profile: ProviderProfile) -> tuple[str, str, str]:
    """Return (api_key_value, api_key_source, api_key_env_var_used) for a provider profile.

    Priority:
    1. Process environment variable (checked in declared order)
    2. .env.atlas via get_secret (checked in declared order)
    3. Missing

    Source strings: "process_env", "env_atlas", "missing", "none"
    """
    if profile.auth_type == "none" or not profile.key_required:
        return ("", "none", "")

    for var_name in profile.api_key_env_vars:
        val = os.getenv(var_name)
        if val:
            return (val, "process_env", var_name)

    # Fallback to .env.atlas via get_secret (which reads from .env.atlas if env is missing)
    for var_name in profile.api_key_env_vars:
        val = get_secret(var_name)
        if val:
            return (val, "env_atlas", var_name)

    return ("", "missing", "")


def _resolve_base_url(profile: ProviderProfile) -> str:
    """Return base URL from env var, profile default, or empty string."""
    if profile.base_url_env_var:
        env_val = os.getenv(profile.base_url_env_var)
        if env_val:
            return env_val
    return profile.base_url


def _resolve_headers(profile: ProviderProfile) -> dict[str, str]:
    """Return provider-specific metadata headers (no secrets)."""
    headers: dict[str, str] = {}
    if profile.id == "openrouter":
        site_url = os.getenv("OPENROUTER_SITE_URL", "")
        site_name = os.getenv("OPENROUTER_SITE_NAME", "")
        if site_url:
            headers["HTTP-Referer"] = site_url
        if site_name:
            headers["X-OpenRouter-Title"] = site_name
    return headers


def _gemini_key_conflict_warning() -> str | None:
    """Warn if both GOOGLE_API_KEY and GEMINI_API_KEY are present.

    Google SDK precedence: GOOGLE_API_KEY takes precedence when both exist.
    """
    has_google = bool(os.getenv("GOOGLE_API_KEY"))
    has_gemini = bool(os.getenv("GEMINI_API_KEY"))
    if has_google and has_gemini:
        return "Both GOOGLE_API_KEY and GEMINI_API_KEY are set; GOOGLE_API_KEY takes precedence."
    return None


def resolve_runtime_provider(
    config: AtlasConfig | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Resolve effective provider, model, URL, API key, and headers for runtime use.

    Priority:
    1. Explicit provider/model arguments override everything.
    2. Config values (from .atlas/config.toml + env).
    3. Provider defaults.

    The returned dict never exposes the raw API key in a context suitable for
    CLI display; callers must treat the 'api_key' field as sensitive.
    """
    # Start from config if available
    cfg_provider = ""
    cfg_model = ""
    if config is not None:
        cfg_provider = (config.model.provider or "").lower().strip()
        cfg_model = (config.model.model or "").strip()

    # Explicit overrides
    requested_provider = (provider or cfg_provider or "openai").lower().strip()
    canonical_provider = normalize_provider_id(requested_provider)

    profile = get_provider_profile(canonical_provider)
    if profile is None:
        # Unknown provider: return best-effort with raw config values
        return {
            "provider": canonical_provider,
            "model": model or cfg_model or "",
            "api_mode": "chat_completions",
            "base_url": "",
            "api_key": "",
            "api_key_source": "missing",
            "api_key_env_var_used": "",
            "auth_header_type": "bearer",
            "headers": {},
            "requested_provider": requested_provider,
            "warnings": [],
        }

    # Resolve model: explicit arg > config > provider default
    effective_model = model or cfg_model or profile.default_model or ""

    # Resolve base URL, API key, headers
    base_url = _resolve_base_url(profile)
    api_key, api_key_source, api_key_env_var_used = _resolve_api_key(profile)
    headers = _resolve_headers(profile)

    warnings: list[str] = []
    if profile.id == "google-gemini":
        gemini_warn = _gemini_key_conflict_warning()
        if gemini_warn:
            warnings.append(gemini_warn)

    return {
        "provider": profile.id,
        "model": effective_model,
        "api_mode": profile.api_mode,
        "base_url": base_url,
        "api_key": api_key,
        "api_key_source": api_key_source,
        "api_key_env_var_used": api_key_env_var_used,
        "auth_header_type": profile.auth_header_type,
        "headers": headers,
        "requested_provider": requested_provider,
        "warnings": warnings,
    }
