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
    if profile.auth_header_type == "none" and not profile.key_required:
        return ("", "none", "")

    # Priority 1: Check process environment
    for var_name in profile.env_precedence:
        val = os.getenv(var_name)
        if val:
            return (val, "process_env", var_name)

    # Priority 2: Fallback to .env.atlas
    for var_name in profile.env_precedence:
        val = get_secret(var_name)
        if val:
            return (val, "env_atlas", var_name)

    if not profile.key_required:
        return ("", "missing", "")

    return ("", "missing", "")


def _resolve_base_url(profile: ProviderProfile, user_provided_base_url: str = "") -> str:
    """Return base URL from config override or profile default."""
    if user_provided_base_url:
        return user_provided_base_url
    return profile.base_url


def _resolve_headers(profile: ProviderProfile) -> dict[str, str]:
    """Return provider-specific required and metadata headers (no secrets)."""
    headers: dict[str, str] = {}
    
    # 1. Apply required headers from profile
    if profile.required_headers:
        headers.update(profile.required_headers)
        
    # 2. Apply optional metadata from environment
    if profile.optional_metadata_env_vars:
        for env_var in profile.optional_metadata_env_vars:
            val = os.getenv(env_var)
            if val:
                # E.g. OPENROUTER_HTTP_REFERER -> HTTP-Referer
                if "HTTP_REFERER" in env_var:
                    headers["HTTP-Referer"] = val
                elif "APP_TITLE" in env_var or "SITE_NAME" in env_var:
                    headers["X-OpenRouter-Title"] = val
                elif "SITE_URL" in env_var:
                    headers["HTTP-Referer"] = val

    return headers


def _check_warnings(profile: ProviderProfile) -> list[str]:
    """Check for provider-specific warnings like ignored aliases."""
    warnings: list[str] = []
    
    if profile.canonical_env_var and profile.accepted_env_aliases:
        has_canonical = bool(os.getenv(profile.canonical_env_var) or get_secret(profile.canonical_env_var))
        for alias in profile.accepted_env_aliases:
            has_alias = bool(os.getenv(alias) or get_secret(alias))
            if has_canonical and has_alias:
                warnings.append(f"Both {profile.canonical_env_var} and {alias} are set; {profile.canonical_env_var} takes precedence.")
            elif has_canonical and not has_alias and profile.id == "google-gemini":
                # Special case: Google Gemini docs say GOOGLE_API_KEY takes precedence
                pass

    return warnings


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
    cfg_base_url = ""
    if config is not None:
        cfg_provider = (config.model.provider or "").lower().strip()
        cfg_model = (config.model.model or "").strip()
        
        # Check provider-specific base_url override if present
        if cfg_provider and hasattr(config, "providers"):
            provider_cfg = getattr(config.providers, cfg_provider.replace("-", "_"), None)
            if provider_cfg and hasattr(provider_cfg, "base_url"):
                cfg_base_url = provider_cfg.base_url

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
            "base_url": cfg_base_url,
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
    base_url = _resolve_base_url(profile, cfg_base_url)
    api_key, api_key_source, api_key_env_var_used = _resolve_api_key(profile)
    headers = _resolve_headers(profile)

    warnings = _check_warnings(profile)

    auth_header_type = profile.auth_header_type
    # If key is missing for openai-compatible/custom, do not emit auth header
    if profile.id in ("openai-compatible", "custom") and not api_key:
        auth_header_type = "none"

    return {
        "provider": profile.id,
        "model": effective_model,
        "api_mode": profile.api_mode,
        "base_url": base_url,
        "api_key": api_key,
        "api_key_source": api_key_source,
        "api_key_env_var_used": api_key_env_var_used,
        "auth_header_type": auth_header_type,
        "headers": headers,
        "requested_provider": requested_provider,
        "warnings": warnings,
    }
