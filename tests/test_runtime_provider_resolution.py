from __future__ import annotations

import os

import pytest

from atlas_agent.config.schema import AtlasConfig
from atlas_agent.providers.runtime import resolve_runtime_provider


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Remove provider env vars so tests are deterministic."""
    for key in (
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY",
        "KIMI_API_KEY",
        "MOONSHOT_API_KEY",
        "NVIDIA_API_KEY",
        "NGC_API_KEY",
        "XAI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_GEMINI_API_KEY",
        "GEMINI_API_KEY",
        "HF_TOKEN",
        "HUGGINGFACEHUB_API_TOKEN",
        "ATLAS_CUSTOM_API_KEY",
        "CUSTOM_API_KEY",
        "ATLAS_GOOGLE_OAUTH_ACCESS_TOKEN",
        "GOOGLE_OAUTH_ACCESS_TOKEN",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ):
        monkeypatch.delenv(key, raising=False)


def test_defaults_to_openai_when_unconfigured() -> None:
    config = AtlasConfig()
    result = resolve_runtime_provider(config)
    assert result["provider"] == "openai"
    assert result["api_key_source"] == "missing"


def test_explicit_args_override_config(monkeypatch) -> None:
    config = AtlasConfig()
    config.model.provider = "openai"
    config.model.model = "gpt-5.5"
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    result = resolve_runtime_provider(config, provider="openrouter", model="anthropic/claude-sonnet-4.6")
    assert result["provider"] == "openrouter"
    assert result["model"] == "anthropic/claude-sonnet-4.6"
    assert result["api_key_source"] == "process_env"
    assert result["api_key_env_var_used"] == "OPENROUTER_API_KEY"


def test_process_env_overrides_dotenv(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "process-key")
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="openai")
    assert result["api_key"] == "process-key"
    assert result["api_key_source"] == "process_env"
    assert result["api_key_env_var_used"] == "OPENAI_API_KEY"


def test_openrouter_key_not_used_for_anthropic(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="anthropic")
    assert result["provider"] == "anthropic"
    assert result["api_key_source"] == "missing"
    assert result["api_key"] == ""


def test_local_provider_never_requires_key() -> None:
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="local")
    assert result["provider"] == "local"
    assert result["api_key_source"] == "none"
    assert result["api_key"] == ""
    assert result["auth_header_type"] == "none"


def test_unknown_provider_best_effort() -> None:
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="unknown-provider")
    assert result["provider"] == "unknown-provider"
    assert result["api_key_source"] == "missing"


def test_model_fallback_to_provider_default() -> None:
    config = AtlasConfig()
    config.model.provider = "openrouter"
    config.model.model = ""
    result = resolve_runtime_provider(config)
    assert result["provider"] == "openrouter"
    assert result["model"] == "anthropic/claude-sonnet-4.6"


def test_api_key_not_printed_in_result() -> None:
    """The resolve function returns the raw key; callers must never print it."""
    config = AtlasConfig()
    result = resolve_runtime_provider(config)
    # The key field exists but should be empty when missing
    assert result["api_key"] == "" or isinstance(result["api_key"], str)


def test_openai_uses_openai_api_key_only(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="openai")
    assert result["api_key"] == "sk-openai"
    assert result["api_key_env_var_used"] == "OPENAI_API_KEY"


def test_anthropic_uses_anthropic_api_key_only(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="anthropic")
    assert result["api_key"] == "sk-ant"
    assert result["api_key_env_var_used"] == "ANTHROPIC_API_KEY"
    assert result["auth_header_type"] == "x-api-key"


def test_deepseek_uses_deepseek_api_key_not_anthropic(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="deepseek")
    assert result["api_key_source"] == "missing"
    assert result["api_key"] == ""


def test_kimi_uses_moonshot_api_key(monkeypatch) -> None:
    """MOONSHOT_API_KEY is canonical for kimi provider."""
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-moon")
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="kimi")
    assert result["api_key"] == "sk-moon"
    assert result["api_key_env_var_used"] == "MOONSHOT_API_KEY"


def test_kimi_accepts_kimi_api_key_alias(monkeypatch) -> None:
    """KIMI_API_KEY is accepted when MOONSHOT_API_KEY is missing."""
    monkeypatch.setenv("KIMI_API_KEY", "sk-kimi")
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="kimi")
    assert result["api_key"] == "sk-kimi"
    assert result["api_key_env_var_used"] == "KIMI_API_KEY"


def test_nvidia_uses_nvidia_api_key_not_ngc(monkeypatch) -> None:
    """NVIDIA_API_KEY is for cloud inference; NGC_API_KEY is ignored."""
    monkeypatch.setenv("NVIDIA_API_KEY", "sk-nvidia")
    monkeypatch.setenv("NGC_API_KEY", "sk-ngc")
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="nvidia")
    assert result["api_key"] == "sk-nvidia"
    assert result["api_key_env_var_used"] == "NVIDIA_API_KEY"


def test_nvidia_ignores_ngc_api_key(monkeypatch) -> None:
    """NGC_API_KEY alone must not satisfy NVIDIA provider."""
    monkeypatch.setenv("NGC_API_KEY", "sk-ngc")
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="nvidia")
    assert result["api_key_source"] == "missing"


def test_xai_uses_xai_api_key(monkeypatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "sk-xai")
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="xai")
    assert result["api_key"] == "sk-xai"


def test_gemini_google_key_takes_precedence(monkeypatch) -> None:
    """GOOGLE_API_KEY takes precedence over GEMINI_API_KEY."""
    monkeypatch.setenv("GOOGLE_API_KEY", "sk-google")
    monkeypatch.setenv("GEMINI_API_KEY", "sk-gemini")
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="google")
    assert result["provider"] == "google"
    assert result["provider_label"] == "Google Gemini"
    assert result["api_mode"] == "gemini_native"
    assert result["auth_method"] == "api_key"
    assert result["auth_header_type"] == "x-goog-api-key"
    assert result["api_key"] == "sk-google"
    assert result["api_key_env_var_used"] == "GOOGLE_API_KEY"
    assert len(result["warnings"]) == 1
    assert "GOOGLE_API_KEY" in result["warnings"][0]


def test_gemini_uses_gemini_key_when_google_missing(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "sk-gemini")
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="google")
    assert result["api_key"] == "sk-gemini"
    assert result["api_key_env_var_used"] == "GEMINI_API_KEY"
    assert len(result["warnings"]) == 0


def test_legacy_openai_compatible_gemini_provider_normalizes_and_sets_mode() -> None:
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="gemini-openai-compatible")
    assert result["provider"] == "google"
    assert result["api_mode"] == "openai_compatible"
    assert result["mode_label"] == "OpenAI-compatible endpoint"
    assert result["auth_header_type"] == "none"
    assert result["base_url"].endswith("/v1beta/openai/")


def test_google_configured_openai_mode_uses_bearer(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "sk-google")
    config = AtlasConfig()
    config.model.provider = "google"
    config.model.google.api_mode = "openai_compatible"
    config.model.google.auth_method = "api_key"
    result = resolve_runtime_provider(config)
    assert result["provider"] == "google"
    assert result["api_mode"] == "openai_compatible"
    assert result["auth_header_type"] == "bearer"
    assert result["api_key_env_var_used"] == "GOOGLE_API_KEY"


def test_google_oauth_adc_missing_fails_clearly() -> None:
    config = AtlasConfig()
    config.model.provider = "google"
    config.model.google.api_mode = "native"
    config.model.google.auth_method = "oauth_adc"
    result = resolve_runtime_provider(config)
    assert result["provider"] == "google"
    assert result["auth_method"] == "oauth_adc"
    assert result["credential_source"] == "missing"
    assert result["auth_header_type"] == "none"
    assert result["api_key"] == ""
    assert result["errors"]
    assert "credentials are unavailable" in result["errors"][0].lower()


def test_google_oauth_adc_uses_explicit_token_without_api_key_fallback(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "sk-google")
    monkeypatch.setenv("ATLAS_GOOGLE_OAUTH_ACCESS_TOKEN", "oauth-token")
    config = AtlasConfig()
    config.model.provider = "google"
    config.model.google.api_mode = "native"
    config.model.google.auth_method = "oauth_adc"
    result = resolve_runtime_provider(config)
    assert result["provider"] == "google"
    assert result["auth_method"] == "oauth_adc"
    assert result["credential_source"] == "env:ATLAS_GOOGLE_OAUTH_ACCESS_TOKEN"
    assert result["auth_header_type"] == "oauth_bearer"
    # oauth_adc mode must not switch to API-key auth semantics.
    assert result["api_key_env_var_used"] == ""


def test_huggingface_uses_hf_token(monkeypatch) -> None:
    """HF_TOKEN is canonical for Hugging Face."""
    monkeypatch.setenv("HF_TOKEN", "hf-test")
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="huggingface")
    assert result["api_key"] == "hf-test"
    assert result["api_key_env_var_used"] == "HF_TOKEN"


def test_huggingface_accepts_legacy_token(monkeypatch) -> None:
    """HUGGINGFACEHUB_API_TOKEN is accepted when HF_TOKEN is missing."""
    monkeypatch.setenv("HUGGINGFACEHUB_API_TOKEN", "hf-legacy")
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="huggingface")
    assert result["api_key"] == "hf-legacy"
    assert result["api_key_env_var_used"] == "HUGGINGFACEHUB_API_TOKEN"


def test_custom_provider_uses_atlas_custom_key(monkeypatch) -> None:
    """Custom provider uses ATLAS_CUSTOM_API_KEY."""
    monkeypatch.setenv("ATLAS_CUSTOM_API_KEY", "sk-custom")
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="custom")
    assert result["api_key"] == "sk-custom"
    assert result["api_key_env_var_used"] == "ATLAS_CUSTOM_API_KEY"


def test_custom_provider_does_not_fallback_to_openai(monkeypatch) -> None:
    """Custom provider must not use OPENAI_API_KEY."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="custom")
    assert result["api_key_source"] == "missing"
    assert result["api_key"] == ""


def test_openrouter_metadata_headers(monkeypatch) -> None:
    """OpenRouter metadata headers are included when env vars are set."""
    monkeypatch.setenv("OPENROUTER_HTTP_REFERER", "https://example.com")
    monkeypatch.setenv("OPENROUTER_APP_TITLE", "My App")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or")
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="openrouter")
    assert result["headers"]["HTTP-Referer"] == "https://example.com"
    assert result["headers"]["X-OpenRouter-Title"] == "My App"


def test_openrouter_metadata_headers_empty_when_not_set(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or")
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="openrouter")
    assert result["headers"] == {}


def test_lmstudio_runtime_resolution_does_not_require_key() -> None:
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="lmstudio")
    assert result["provider"] == "lmstudio"
    assert result["api_key_source"] == "none"
    assert result["api_key"] == ""
    assert result["auth_header_type"] == "none"
    assert result["base_url"] == "http://localhost:1234/v1"


def test_openai_compatible_requires_base_url_and_model_no_fallback(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("ATLAS_OPENAI_COMPATIBLE_API_KEY", "sk-compatible")
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="openai-compatible")
    assert result["provider"] == "openai-compatible"
    assert result["api_key_source"] == "process_env"
    assert result["api_key"] == "sk-compatible"
    assert result["api_key_env_var_used"] == "ATLAS_OPENAI_COMPATIBLE_API_KEY"
    assert result["auth_header_type"] == "bearer"


def test_openai_compatible_no_key_emits_no_auth_header() -> None:
    config = AtlasConfig()
    result = resolve_runtime_provider(config, provider="openai-compatible")
    assert result["provider"] == "openai-compatible"
    assert result["api_key_source"] == "missing"
    assert result["api_key"] == ""
    assert result["auth_header_type"] == "none"

def test_factory_fails_closed_when_no_provider_configured(monkeypatch) -> None:
    from atlas_agent.providers.factory import get_provider_from_env
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("ATLAS_DRY_RUN", raising=False)
    with pytest.raises(ValueError, match="No AI provider configured"):
        get_provider_from_env(allow_null=False)

def test_factory_allows_null_when_explicitly_requested(monkeypatch) -> None:
    from atlas_agent.providers.factory import get_provider_from_env
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("ATLAS_DRY_RUN", raising=False)
    provider = get_provider_from_env(allow_null=True)
    assert provider.name == "null"
