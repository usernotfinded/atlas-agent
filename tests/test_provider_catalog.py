from __future__ import annotations

import pytest

from atlas_agent.providers.catalog import (
    list_provider_profiles,
    get_provider_profile,
    normalize_provider_id,
    provider_model_ids,
    default_model_for_provider,
    is_known_model_for_provider,
)


def test_list_includes_major_providers() -> None:
    ids = {p.id for p in list_provider_profiles()}
    assert "openrouter" in ids
    assert "openai" in ids
    assert "anthropic" in ids
    assert "deepseek" in ids
    assert "kimi" in ids
    assert "nvidia" in ids
    assert "xai" in ids
    assert "google-gemini" in ids
    assert "huggingface" in ids
    assert "local" in ids
    assert "custom" in ids


def test_alias_normalization() -> None:
    assert normalize_provider_id("or") == "openrouter"
    assert normalize_provider_id("claude") == "anthropic"
    assert normalize_provider_id("ds") == "deepseek"
    assert normalize_provider_id("moonshot") == "kimi"
    assert normalize_provider_id("nim") == "nvidia"
    assert normalize_provider_id("grok") == "xai"
    assert normalize_provider_id("gemini") == "google-gemini"
    assert normalize_provider_id("google") == "google-gemini"
    assert normalize_provider_id("hf") == "huggingface"
    assert normalize_provider_id("ollama") == "local"
    assert normalize_provider_id("UNKNOWN") == "unknown"


def test_get_profile_by_id_and_alias() -> None:
    assert get_provider_profile("openrouter") is not None
    assert get_provider_profile("or") is not None
    assert get_provider_profile("nonexistent") is None


def test_model_list_returns_defaults() -> None:
    models = provider_model_ids("openrouter")
    assert "openai/gpt-5.5" in models
    assert "anthropic/claude-sonnet-4.6" in models

    models = provider_model_ids("openai")
    assert "gpt-5.5" in models


def test_default_model_exists_in_catalog() -> None:
    for profile in list_provider_profiles():
        if profile.models:
            assert is_known_model_for_provider(profile.id, profile.default_model)


def test_unknown_provider_returns_empty() -> None:
    assert provider_model_ids("nonexistent") == []
    assert default_model_for_provider("nonexistent") == ""
    assert not is_known_model_for_provider("nonexistent", "anything")


def test_provider_profile_fields() -> None:
    p = get_provider_profile("openrouter")
    assert p is not None
    assert p.auth_type == "api_key"
    assert p.api_mode == "chat_completions"
    assert p.auth_header_type == "bearer"
    assert p.key_required is True
    assert p.base_url != ""
    assert p.api_key_env_vars
    assert p.optional_metadata_env_vars


def test_local_provider_has_no_auth() -> None:
    p = get_provider_profile("local")
    assert p is not None
    assert p.auth_type == "none"
    assert p.auth_header_type == "none"
    assert p.key_required is False
    assert p.api_key_env_vars == ()


def test_kimi_canonical_env_var() -> None:
    """MOONSHOT_API_KEY is canonical; KIMI_API_KEY is accepted alias."""
    p = get_provider_profile("kimi")
    assert p is not None
    assert p.api_key_env_vars[0] == "MOONSHOT_API_KEY"
    assert "KIMI_API_KEY" in p.api_key_env_vars


def test_nvidia_does_not_include_ngc() -> None:
    """NGC_API_KEY must not be in NVIDIA provider env vars."""
    p = get_provider_profile("nvidia")
    assert p is not None
    assert "NVIDIA_API_KEY" in p.api_key_env_vars
    assert "NGC_API_KEY" not in p.api_key_env_vars


def test_huggingface_uses_hf_token() -> None:
    """HF_TOKEN is canonical; HUGGINGFACEHUB_API_TOKEN is legacy alias."""
    p = get_provider_profile("huggingface")
    assert p is not None
    assert p.api_key_env_vars[0] == "HF_TOKEN"
    assert "HUGGINGFACEHUB_API_TOKEN" in p.api_key_env_vars
    assert "HF_API_KEY" not in p.api_key_env_vars


def test_gemini_env_var_order() -> None:
    """GOOGLE_API_KEY takes precedence over GEMINI_API_KEY."""
    p = get_provider_profile("google-gemini")
    assert p is not None
    assert p.api_key_env_vars[0] == "GOOGLE_API_KEY"
    assert "GEMINI_API_KEY" in p.api_key_env_vars


def test_custom_provider_key() -> None:
    """Custom provider uses ATLAS_CUSTOM_API_KEY."""
    p = get_provider_profile("custom")
    assert p is not None
    assert p.api_key_env_vars == ("ATLAS_CUSTOM_API_KEY",)


def test_openrouter_metadata_env_vars() -> None:
    """OpenRouter has optional metadata env vars that are not secrets."""
    p = get_provider_profile("openrouter")
    assert p is not None
    assert "OPENROUTER_SITE_URL" in p.optional_metadata_env_vars
    assert "OPENROUTER_SITE_NAME" in p.optional_metadata_env_vars
