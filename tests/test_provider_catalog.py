from __future__ import annotations

from atlas_agent.providers.catalog import (
    infer_google_api_mode,
    list_provider_profiles,
    get_provider_profile,
    normalize_provider_id,
    provider_model_ids,
    default_model_for_provider,
    is_known_model_for_provider,
    provider_allows_custom_model,
    validate_model_for_provider,
)

OPENROUTER_IDS = {
    "openai/gpt-5.5",
    "openai/gpt-5.4",
    "openai/gpt-5",
    "openai/gpt-4o",
    "anthropic/claude-opus-4-7",
    "anthropic/claude-sonnet-4-6",
    "anthropic/claude-haiku-4-5",
    "google/gemini-3.1-pro-preview",
    "google/gemini-3-flash-preview",
    "google/gemini-2.5-pro",
    "deepseek/deepseek-v4-pro",
    "deepseek/deepseek-v4-flash",
    "moonshotai/kimi-k2.6",
    "x-ai/grok-4.3",
    "qwen/qwen3.6-35b-a3b",
    "meta-llama/llama-3.3-70b-instruct",
}


OPENAI_IDS = {
    "gpt-5.5",
    "gpt-5.5-pro",
    "gpt-5.4",
    "gpt-5.4-pro",
    "gpt-5.4-mini",
    "gpt-5.4-nano",
    "gpt-5",
    "gpt-5-pro",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-4.1",
    "gpt-4o",
    "gpt-4o-mini",
    "o3-pro",
    "o3",
    "gpt-5.3-codex",
    "gpt-oss-120b",
    "gpt-oss-20b",
}

ANTHROPIC_IDS = {
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
    "claude-haiku-4-5-20251001",
}

GOOGLE_IDS = {
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
}

DEEPSEEK_IDS = {
    "deepseek-v4-pro",
    "deepseek-v4-flash",
}

KIMI_IDS = {
    "kimi-k2.6",
    "kimi-k2.5",
    "moonshot-v1-8k",
    "moonshot-v1-32k",
    "moonshot-v1-128k",
}

XAI_IDS = {
    "grok-4.3",
    "grok-4.20",
    "grok-4.20-reasoning",
    "grok-4.20-non-reasoning",
}

NVIDIA_TEXT_EXAMPLE_IDS = {
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/nemotron-3-nano-30b-a3b",
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "gemma-4-31b-it",
    "minimax-m2.7",
}

HF_TEXT_EXAMPLE_IDS = {
    "deepseek-ai/DeepSeek-V4-Pro",
    "deepseek-ai/DeepSeek-V4-Flash",
    "Qwen/Qwen3.6-35B-A3B",
    "google/gemma-4-31B-it",
    "google/gemma-4-26B-A4B-it",
    "moonshotai/Kimi-K2.6",
    "moonshotai/Kimi-K2-Instruct-0905",
    "zai-org/GLM-5.1",
}

LMSTUDIO_EXAMPLE_IDS = {
    "llama",
    "qwen",
    "gemma",
    "mistral",
    "deepseek",
    "phi",
    "yi",
    "nous-hermes",
}

OPENAI_COMPATIBLE_EXAMPLE_IDS = {
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "kimi-k2.6",
    "Qwen/Qwen3.6-35B-A3B",
    "google/gemma-4-31B-it",
    "local-model",
    "custom-model",
}

CUSTOM_ENDPOINT_EXAMPLE_IDS = {
    "custom-model",
    "local-model",
    "deployed-model",
    "Qwen/Qwen3.6-35B-A3B",
    "deepseek-v4-flash",
}

NVIDIA_LOCAL_EXAMPLE_IDS = {
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/nemotron-3-nano-30b-a3b",
    "deepseek-v4-flash",
    "deepseek-v4-pro",
}


def _all_catalog_model_ids() -> set[str]:
    ids: set[str] = set()
    for profile in list_provider_profiles():
        ids.update(m.id for m in profile.models)
    return ids


def test_list_includes_major_providers() -> None:
    ids = {p.id for p in list_provider_profiles()}
    assert "openrouter" in ids
    assert "openai" in ids
    assert "anthropic" in ids
    assert "deepseek" in ids
    assert "kimi" in ids
    assert "nvidia" in ids
    assert "xai" in ids
    assert "google" in ids
    assert "google-gemini" not in ids
    assert "gemini-openai-compatible" not in ids
    assert "huggingface" in ids
    assert "lmstudio" in ids
    assert "openai-compatible" in ids
    assert "custom" in ids


def test_alias_normalization() -> None:
    assert normalize_provider_id("or") == "openrouter"
    assert normalize_provider_id("claude") == "anthropic"
    assert normalize_provider_id("ds") == "deepseek"
    assert normalize_provider_id("moonshot") == "kimi"
    assert normalize_provider_id("nim") == "nvidia"
    assert normalize_provider_id("grok") == "xai"
    assert normalize_provider_id("gemini") == "google"
    assert normalize_provider_id("google") == "google"
    assert normalize_provider_id("google-gemini") == "google"
    assert normalize_provider_id("gemini-openai-compatible") == "google"
    assert normalize_provider_id("google-gemini-openai-compatible") == "google"
    assert normalize_provider_id("hf") == "huggingface"
    assert normalize_provider_id("ollama") == "local"
    assert normalize_provider_id("lm-studio") == "lmstudio"
    assert normalize_provider_id("openai_compatible") == "openai-compatible"
    assert normalize_provider_id("UNKNOWN") == "unknown"


def test_get_profile_by_id_and_alias() -> None:
    assert get_provider_profile("openrouter") is not None
    assert get_provider_profile("or") is not None
    assert get_provider_profile("nonexistent") is None


def test_every_model_label_is_exact_model_id() -> None:
    for profile in list_provider_profiles():
        for model in profile.models:
            assert model.label == model.id


def test_openai_catalog_text_ids_only() -> None:
    assert set(provider_model_ids("openai")) == OPENAI_IDS


def test_openrouter_catalog_curated_text_examples_only() -> None:
    assert set(provider_model_ids("openrouter")) == OPENROUTER_IDS


def test_anthropic_catalog_text_ids_only() -> None:
    assert set(provider_model_ids("anthropic")) == ANTHROPIC_IDS


def test_google_catalog_text_ids_only() -> None:
    assert set(provider_model_ids("google")) == GOOGLE_IDS


def test_deepseek_catalog_text_ids_only() -> None:
    assert set(provider_model_ids("deepseek")) == DEEPSEEK_IDS


def test_kimi_catalog_text_ids_only() -> None:
    assert set(provider_model_ids("kimi")) == KIMI_IDS


def test_xai_catalog_text_ids_only() -> None:
    assert set(provider_model_ids("xai")) == XAI_IDS


def test_nvidia_catalog_curated_text_examples_only() -> None:
    assert set(provider_model_ids("nvidia")) == NVIDIA_TEXT_EXAMPLE_IDS


def test_huggingface_catalog_curated_text_examples_only() -> None:
    assert set(provider_model_ids("huggingface")) == HF_TEXT_EXAMPLE_IDS


def test_lmstudio_catalog_curated_examples_only() -> None:
    assert set(provider_model_ids("lmstudio")) == LMSTUDIO_EXAMPLE_IDS


def test_openai_compatible_catalog_curated_examples_only() -> None:
    assert set(provider_model_ids("openai-compatible")) == OPENAI_COMPATIBLE_EXAMPLE_IDS


def test_custom_endpoint_catalog_curated_examples_only() -> None:
    assert set(provider_model_ids("custom")) == CUSTOM_ENDPOINT_EXAMPLE_IDS


def test_nvidia_local_catalog_curated_examples_only() -> None:
    assert set(provider_model_ids("nvidia-local")) == NVIDIA_LOCAL_EXAMPLE_IDS


def test_provider_defaults_are_provider_valid() -> None:
    for profile in list_provider_profiles():
        if not profile.include_in_model_providers_default:
            continue
        default_id = default_model_for_provider(profile.id)
        if not default_id:
            continue
        ok, err = validate_model_for_provider(profile.id, default_id)
        assert ok is True, f"{profile.id} default invalid: {err}"


def test_expected_provider_defaults() -> None:
    assert default_model_for_provider("anthropic") == "claude-opus-4-7"
    assert default_model_for_provider("openai") == "gpt-5.5"
    assert default_model_for_provider("deepseek") == "deepseek-v4-pro"
    assert default_model_for_provider("google") == "gemini-3.1-pro-preview"
    assert default_model_for_provider("kimi") == "kimi-k2.6"
    assert default_model_for_provider("xai") == "grok-4.3"
    assert default_model_for_provider("huggingface") == "Qwen/Qwen3.6-35B-A3B"
    assert default_model_for_provider("nvidia") == "nvidia/llama-3.3-nemotron-super-49b-v1.5"


def test_freeform_defaults_are_empty() -> None:
    assert default_model_for_provider("lmstudio") == ""
    assert default_model_for_provider("local") == ""
    assert default_model_for_provider("openai-compatible") == ""
    assert default_model_for_provider("custom") == ""
    assert default_model_for_provider("nvidia-local") == ""


def test_unknown_provider_returns_empty() -> None:
    assert provider_model_ids("nonexistent") == []
    assert default_model_for_provider("nonexistent") == ""
    assert not is_known_model_for_provider("nonexistent", "anything")


def test_provider_profile_fields() -> None:
    p = get_provider_profile("openrouter")
    assert p is not None
    assert p.auth_header_type == "bearer"
    assert p.api_mode == "chat_completions"
    assert p.key_required is True
    assert p.base_url != ""
    assert p.env_precedence
    assert p.optional_metadata_env_vars


def test_local_provider_has_no_auth() -> None:
    p = get_provider_profile("local")
    assert p is not None
    assert p.auth_header_type == "none"
    assert p.key_required is False
    assert p.env_precedence == ()


def test_kimi_canonical_env_var() -> None:
    p = get_provider_profile("kimi")
    assert p is not None
    assert p.env_precedence[0] == "MOONSHOT_API_KEY"
    assert "KIMI_API_KEY" in p.env_precedence


def test_nvidia_does_not_include_ngc() -> None:
    p = get_provider_profile("nvidia")
    assert p is not None
    assert "NVIDIA_API_KEY" in p.env_precedence
    assert "NGC_API_KEY" not in p.env_precedence


def test_huggingface_uses_hf_token() -> None:
    p = get_provider_profile("huggingface")
    assert p is not None
    assert p.env_precedence[0] == "HF_TOKEN"
    assert "HUGGINGFACEHUB_API_TOKEN" in p.env_precedence
    assert "HF_API_KEY" not in p.env_precedence


def test_gemini_env_var_order() -> None:
    p = get_provider_profile("google")
    assert p is not None
    assert p.env_precedence[0] == "GOOGLE_API_KEY"
    assert "GEMINI_API_KEY" in p.env_precedence


def test_gemini_mode_inference_for_legacy_ids() -> None:
    assert infer_google_api_mode("google-gemini") == "native"
    assert infer_google_api_mode("gemini") == "native"
    assert infer_google_api_mode("gemini-openai-compatible") == "openai_compatible"
    assert infer_google_api_mode("google-gemini-openai-compatible") == "openai_compatible"


def test_custom_provider_key() -> None:
    p = get_provider_profile("custom")
    assert p is not None
    assert p.env_precedence == ("ATLAS_CUSTOM_API_KEY",)


def test_lmstudio_profile() -> None:
    p = get_provider_profile("lmstudio")
    assert p is not None
    assert p.auth_header_type == "none"
    assert p.key_required is False
    assert p.base_url == "http://localhost:1234/v1"
    assert p.env_precedence == ()


def test_openai_compatible_profile() -> None:
    p = get_provider_profile("openai-compatible")
    assert p is not None
    assert p.key_required is False
    assert "ATLAS_OPENAI_COMPATIBLE_API_KEY" in p.env_precedence
    assert "OPENAI_API_KEY" not in p.env_precedence


def test_openrouter_metadata_env_vars() -> None:
    p = get_provider_profile("openrouter")
    assert p is not None
    assert "OPENROUTER_HTTP_REFERER" in p.optional_metadata_env_vars
    assert "OPENROUTER_APP_TITLE" in p.optional_metadata_env_vars


def test_custom_model_policy_flags() -> None:
    assert provider_allows_custom_model("openrouter") is True
    assert provider_allows_custom_model("huggingface") is True
    assert provider_allows_custom_model("nvidia") is True
    assert provider_allows_custom_model("lmstudio") is True
    assert provider_allows_custom_model("local") is True
    assert provider_allows_custom_model("openai-compatible") is True
    assert provider_allows_custom_model("custom") is True
    assert provider_allows_custom_model("nvidia-local") is True

    assert provider_allows_custom_model("openai") is False
    assert provider_allows_custom_model("anthropic") is False
    assert provider_allows_custom_model("google") is False
    assert provider_allows_custom_model("deepseek") is False
    assert provider_allows_custom_model("kimi") is False
    assert provider_allows_custom_model("xai") is False


def test_validate_model_rejects_cross_provider_pairs() -> None:
    bad_pairs = [
        ("openai", "claude-sonnet-4-6"),
        ("anthropic", "gpt-5.5"),
        ("google", "claude-opus-4-7"),
        ("deepseek", "gpt-4o"),
        ("kimi", "deepseek-v4-pro"),
        ("xai", "gpt-5.5"),
    ]
    for provider, model in bad_pairs:
        ok, err = validate_model_for_provider(provider, model)
        assert ok is False
        assert err is not None
        assert f"provider '{provider}'" in err


def test_validate_model_rejects_unknown_for_hosted_curated_providers() -> None:
    for provider in ("openai", "anthropic", "google", "deepseek", "kimi", "xai"):
        ok, err = validate_model_for_provider(provider, "my-random-model")
        assert ok is False
        assert err is not None


def test_validate_model_allows_freeform_for_compatible_providers() -> None:
    assert validate_model_for_provider("openrouter", "my-arbitrary-model")[0] is True
    assert validate_model_for_provider("huggingface", "my-private-hf-model")[0] is True
    assert validate_model_for_provider("nvidia", "my-nim-cloud-deployment")[0] is True
    assert validate_model_for_provider("openai-compatible", "custom-id")[0] is True
    assert validate_model_for_provider("lmstudio", "my-local-model")[0] is True
    assert validate_model_for_provider("local", "meta-llama/Llama-3.3-70B-Instruct")[0] is True
    assert validate_model_for_provider("nvidia-local", "nvidia/llama-3.3-nemotron-super-49b-v1.5")[0] is True


def test_explicit_absence_of_deprecated_or_non_text_ids() -> None:
    all_ids = _all_catalog_model_ids()

    must_be_absent = {
        "deepseek-chat",
        "deepseek-reasoner",
        "kimi-latest",
        "kimi-thinking-preview",
        "kimi-k2-0905-preview",
        "kimi-k2-0711-preview",
        "kimi-k2-turbo-preview",
        "kimi-k2-thinking",
        "kimi-k2-thinking-turbo",
        "grok-code-fast-1",
        "grok-3",
        "grok-4",
        "claude-3-5-sonnet-20240620",
        "claude-sonnet-4-20250514",
        "gemini-3.1-flash-lite-preview",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gpt-5.2-codex",
        "gpt-5.1-codex",
        "codex-mini-latest",
        "gpt-3.5-turbo",
        "dall-e-3",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
        "llama-nemotron-embed-1b-v2",
        "llama-nemotron-rerank-1b-v2",
        "nemotron-ocr-v1",
        "nemotron-3-content-safety",
        "cosmos-reason2-8b",
    }
    assert must_be_absent.isdisjoint(all_ids)


def test_no_non_text_modalities_in_normal_catalogs() -> None:
    all_ids = {model_id.lower() for model_id in _all_catalog_model_ids()}
    banned_fragments = [
        "embedding",
        "embed",
        "realtime",
        "audio",
        "tts",
        "transcrib",
        "moderation",
        "rerank",
        "ocr",
        "video",
        "music",
        "dall-e",
        "imagen",
        "veo",
        "lyria",
    ]
    for model_id in all_ids:
        assert not any(fragment in model_id for fragment in banned_fragments), model_id
