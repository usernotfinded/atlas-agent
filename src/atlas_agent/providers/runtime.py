# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    providers/runtime.py
# PURPOSE: Works out which provider, model, endpoint and credential a run will
#          actually use — and reports WHERE each came from. The provenance matters:
#          "which key is this agent about to spend money with?" must be answerable
#          without printing the key.
# DEPS:    providers.catalog (the profiles), config.secrets (the .env.atlas store)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from atlas_agent.config.schema import AtlasConfig
from atlas_agent.config.secrets import get_secret
from atlas_agent.providers.catalog import (
    GOOGLE_PROVIDER_ID,
    ProviderProfile,
    get_provider_profile,
    infer_google_api_mode,
    normalize_provider_id,
)


# --- CONFIGURATIONS & CONSTANTS ---

GOOGLE_NATIVE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
GOOGLE_OPENAI_COMPATIBLE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


# ==============================================================================
# CREDENTIAL RESOLUTION
# ==============================================================================

def _resolve_api_key(profile: ProviderProfile) -> tuple[str, str, str]:
    """Return (api_key_value, api_key_source, api_key_env_var_used) for a provider profile.

    Priority:
    1. Process environment variable (checked in declared order)
    2. .env.atlas via get_secret (checked in declared order)
    3. Missing

    Source strings: "process_env", "env_atlas", "missing", "none"
    """
    # The SOURCE is returned alongside the value, and it is the interesting half: the
    # diagnostics surface reports the source and the var NAME, never the key. That is
    # how `atlas model status` can tell you which credential is in play without leaking
    # it into a terminal, a screenshot or a log.
    #
    # "missing" and "none" are distinct: "none" means this provider needs no key (a
    # local model), while "missing" means it needs one and does not have it. Collapsing
    # them would let a misconfigured cloud provider look deliberately keyless.
    if profile.auth_header_type == "none" and not profile.key_required:
        return ("", "none", "")

    # Process env beats .env.atlas, matching load_atlas_secrets(override=False) — one
    # precedence rule for credentials, applied consistently across the project.
    for var_name in profile.env_precedence:
        val = os.getenv(var_name)
        if val:
            return (val, "process_env", var_name)

    # Priority 2: Fallback to .env.atlas
    for var_name in profile.env_precedence:
        val = get_secret(var_name)
        if val:
            return (val, "env_atlas", var_name)

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
                warnings.append(
                    f"Both {profile.canonical_env_var} and {alias} are set; {profile.canonical_env_var} takes precedence."
                )
            elif has_canonical and not has_alias and profile.id == GOOGLE_PROVIDER_ID:
                # No warning required when only canonical key is present.
                pass

    return warnings


def _normalize_google_api_mode(value: str | None) -> str:
    key = (value or "").strip().lower()
    if key in {"openai_compatible", "openai-compatible", "openai", "compat"}:
        return "openai_compatible"
    return "native"


def _normalize_google_auth_method(value: str | None) -> str:
    key = (value or "").strip().lower()
    if key in {"oauth_adc", "oauth", "adc"}:
        return "oauth_adc"
    return "api_key"


def _google_mode_label(api_mode: str) -> str:
    if api_mode == "openai_compatible":
        return "OpenAI-compatible endpoint"
    return "Native Gemini API"


def _resolve_google_oauth_adc() -> tuple[str, str, list[str]]:
    """Resolve Google OAuth/ADC scaffold credentials metadata.

    Returns:
    - credential_source: source label or "missing"
    - auth_header_type: "oauth_bearer" or "none"
    - warnings: remediation warnings when credentials are unavailable
    """
    warnings: list[str] = []

    for env_var in ("ATLAS_GOOGLE_OAUTH_ACCESS_TOKEN", "GOOGLE_OAUTH_ACCESS_TOKEN"):
        token = os.getenv(env_var)
        if token:
            return (f"env:{env_var}", "oauth_bearer", warnings)

    adc_env_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if adc_env_path:
        adc_file = Path(adc_env_path).expanduser()
        if adc_file.exists():
            return (f"adc:{adc_file}", "oauth_bearer", warnings)
        warnings.append(
            f"GOOGLE_APPLICATION_CREDENTIALS is set but the file does not exist: {adc_file}."
        )

    adc_default = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    if adc_default.exists():
        return (f"adc:{adc_default}", "oauth_bearer", warnings)

    warnings.append(
        "Google OAuth/ADC credentials are unavailable. Configure GOOGLE_APPLICATION_CREDENTIALS "
        "or run `gcloud auth application-default login`, then retry."
    )
    return ("missing", "none", warnings)


def _mode_label(profile: ProviderProfile, api_mode: str) -> str:
    if profile.id == GOOGLE_PROVIDER_ID:
        return _google_mode_label(api_mode)
    return api_mode


def resolve_runtime_provider(
    config: AtlasConfig | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Resolve effective provider, model, URL, credentials, and headers for runtime use.

    Priority:
    1. Explicit provider/model arguments override everything.
    2. Config values (from .atlas/config.toml + env).
    3. Provider defaults.

    The returned dict never exposes secrets in any field intended for CLI display.
    """
    cfg_provider = ""
    cfg_model = ""
    cfg_base_url = ""
    cfg_google_api_mode: str | None = None
    cfg_google_auth_method: str | None = None
    cfg_google_base_url = ""

    if config is not None:
        cfg_provider = (config.model.provider or "").lower().strip()
        cfg_model = (config.model.model or "").strip()
        cfg_base_url = (config.model.base_url or "").strip()

        google_cfg = getattr(config.model, "google", None)
        if google_cfg is not None:
            cfg_google_api_mode = getattr(google_cfg, "api_mode", None)
            cfg_google_auth_method = getattr(google_cfg, "auth_method", None)
            cfg_google_base_url = (getattr(google_cfg, "base_url", "") or "").strip()

        # Check provider-specific base_url override if present
        if cfg_provider and hasattr(config, "providers"):
            provider_cfg = getattr(config.providers, cfg_provider.replace("-", "_"), None)
            if provider_cfg and hasattr(provider_cfg, "base_url"):
                cfg_base_url = provider_cfg.base_url or cfg_base_url

    requested_provider = (provider or cfg_provider or "openai").lower().strip()
    canonical_provider = normalize_provider_id(requested_provider)

    profile = get_provider_profile(canonical_provider)
    if profile is None:
        return {
            "provider": canonical_provider,
            "provider_label": canonical_provider,
            "model": model or cfg_model or "",
            "api_mode": "chat_completions",
            "mode_label": "chat_completions",
            "auth_method": "api_key",
            "base_url": cfg_base_url,
            "api_key": "",
            "api_key_source": "missing",
            "credential_source": "missing",
            "api_key_env_var_used": "",
            "auth_header_type": "bearer",
            "headers": {},
            "requested_provider": requested_provider,
            "errors": [],
            "warnings": [],
        }

    effective_model = model or cfg_model or profile.default_model or ""

    effective_api_mode = profile.api_mode
    auth_method = "api_key" if profile.key_required else "none"
    auth_header_type = profile.auth_header_type
    api_key = ""
    api_key_source = "none" if (profile.auth_header_type == "none" and not profile.key_required) else "missing"
    credential_source = api_key_source
    api_key_env_var_used = ""
    errors: list[str] = []
    warnings: list[str] = []

    if profile.id == GOOGLE_PROVIDER_ID:
        inferred_mode = infer_google_api_mode(requested_provider)
        effective_google_mode = _normalize_google_api_mode(cfg_google_api_mode or inferred_mode or "native")
        auth_method = _normalize_google_auth_method(cfg_google_auth_method or "api_key")

        if effective_google_mode == "openai_compatible":
            effective_api_mode = "openai_compatible"
            mode_default_base_url = GOOGLE_OPENAI_COMPATIBLE_BASE_URL
            auth_header_for_api_key = "bearer"
        else:
            effective_api_mode = "gemini_native"
            mode_default_base_url = GOOGLE_NATIVE_BASE_URL
            auth_header_for_api_key = "x-goog-api-key"

        base_url_override = cfg_google_base_url or cfg_base_url
        base_url = base_url_override or mode_default_base_url

        if auth_method == "oauth_adc":
            credential_source, auth_header_type, oauth_warnings = _resolve_google_oauth_adc()
            warnings.extend(oauth_warnings)
            api_key_source = "oauth_adc" if credential_source != "missing" else "missing"
            if credential_source == "missing":
                errors.append(
                    "Google OAuth/ADC authentication is selected but credentials are unavailable."
                )
            api_key = ""
            api_key_env_var_used = ""
        else:
            api_key, api_key_source, api_key_env_var_used = _resolve_api_key(profile)
            credential_source = api_key_source
            auth_header_type = auth_header_for_api_key if api_key else "none"
            warnings.extend(_check_warnings(profile))
    else:
        base_url = _resolve_base_url(profile, cfg_base_url)
        api_key, api_key_source, api_key_env_var_used = _resolve_api_key(profile)
        credential_source = api_key_source
        warnings.extend(_check_warnings(profile))

        # If key is missing for key-optional provider variants, do not emit auth header.
        if profile.id in ("openai-compatible", "custom") and not api_key:
            auth_header_type = "none"

    headers = _resolve_headers(profile)

    return {
        "provider": profile.id,
        "provider_label": profile.label,
        "model": effective_model,
        "api_mode": effective_api_mode,
        "mode_label": _mode_label(profile, effective_api_mode),
        "auth_method": auth_method,
        "base_url": base_url,
        "api_key": api_key,
        "api_key_source": api_key_source,
        "credential_source": credential_source,
        "api_key_env_var_used": api_key_env_var_used,
        "auth_header_type": auth_header_type,
        "headers": headers,
        "requested_provider": requested_provider,
        "errors": errors,
        "warnings": warnings,
    }
