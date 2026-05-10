from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelOption:
    id: str
    label: str = ""
    description: str = ""
    recommended: bool = False
    free: bool = False
    context_window: int | None = None


@dataclass(frozen=True)
class ProviderProfile:
    id: str
    label: str
    auth_type: str  # "api_key", "none", "custom"
    api_mode: str   # "chat_completions", "anthropic_messages", "custom"
    auth_header_type: str  # "bearer", "x-api-key", "none", "custom"
    key_required: bool
    base_url: str = ""
    base_url_env_var: str = ""
    api_key_env_vars: tuple[str, ...] = ()
    optional_metadata_env_vars: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    models: tuple[ModelOption, ...] = ()
    default_model: str = ""
    docs_url: str = ""


# Curated model catalogs — availability depends on provider and account.
# These are common defaults, not guaranteed live inventory.

_OPENROUTER_MODELS = (
    ModelOption("openai/gpt-5.5", label="GPT-5.5", recommended=True),
    ModelOption("anthropic/claude-opus-4.7", label="Claude Opus 4.7"),
    ModelOption("anthropic/claude-sonnet-4.6", label="Claude Sonnet 4.6", recommended=True),
    ModelOption("moonshotai/kimi-k2.6", label="Kimi K2.6"),
    ModelOption("qwen/qwen3.6-plus", label="Qwen 3.6 Plus"),
    ModelOption("deepseek/deepseek-v4-pro", label="DeepSeek V4 Pro"),
    ModelOption("google/gemini-3.1-pro-preview", label="Gemini 3.1 Pro Preview"),
    ModelOption("z-ai/glm-5.1", label="GLM 5.1"),
)

_OPENAI_MODELS = (
    ModelOption("gpt-5.5", label="GPT-5.5", recommended=True),
    ModelOption("gpt-5.4", label="GPT-5.4"),
    ModelOption("gpt-5.4-mini", label="GPT-5.4 Mini"),
    ModelOption("gpt-5.3-codex", label="GPT-5.3 Codex"),
)

_ANTHROPIC_MODELS = (
    ModelOption("claude-opus-4.7", label="Claude Opus 4.7"),
    ModelOption("claude-opus-4.6", label="Claude Opus 4.6"),
    ModelOption("claude-sonnet-4.6", label="Claude Sonnet 4.6", recommended=True),
    ModelOption("claude-haiku-4.5", label="Claude Haiku 4.5"),
)

_DEEPSEEK_MODELS = (
    ModelOption("deepseek-v4-pro", label="DeepSeek V4 Pro", recommended=True),
    ModelOption("deepseek-v4-flash", label="DeepSeek V4 Flash"),
    ModelOption("deepseek-chat", label="DeepSeek Chat"),
    ModelOption("deepseek-reasoner", label="DeepSeek Reasoner"),
)

_KIMI_MODELS = (
    ModelOption("kimi-k2.6", label="Kimi K2.6", recommended=True),
    ModelOption("kimi-k2.5", label="Kimi K2.5"),
    ModelOption("kimi-k2-thinking", label="Kimi K2 Thinking"),
    ModelOption("kimi-k2-turbo-preview", label="Kimi K2 Turbo Preview"),
)

_NVIDIA_MODELS = (
    ModelOption("nvidia/nemotron-3-super-120b-a12b", label="Nemotron 3 Super 120B A12B"),
    ModelOption("moonshotai/kimi-k2.6", label="Kimi K2.6"),
    ModelOption("deepseek-ai/deepseek-v3.2", label="DeepSeek V3.2"),
    ModelOption("qwen/qwen3.5-397b-a17b", label="Qwen 3.5 397B A17B"),
)

_XAI_MODELS = (
    ModelOption("grok-4", label="Grok 4", recommended=True),
    ModelOption("grok-4-fast", label="Grok 4 Fast"),
    ModelOption("grok-code-fast-1", label="Grok Code Fast 1"),
)

_GOOGLE_MODELS = (
    ModelOption("gemini-3.1-pro-preview", label="Gemini 3.1 Pro Preview", recommended=True),
    ModelOption("gemini-3-flash-preview", label="Gemini 3 Flash Preview"),
    ModelOption("gemini-3.1-flash-lite-preview", label="Gemini 3.1 Flash Lite Preview"),
)

_HF_MODELS = (
    ModelOption("moonshotai/Kimi-K2.6", label="Kimi K2.6"),
    ModelOption("Qwen/Qwen3.5-397B-A17B", label="Qwen 3.5 397B A17B"),
    ModelOption("deepseek-ai/DeepSeek-V3.2", label="DeepSeek V3.2"),
)

_LOCAL_MODELS = (
    ModelOption("local/default", label="Local Default"),
)

_CUSTOM_MODELS = (
    ModelOption("custom", label="Custom"),
)


_PROVIDER_PROFILES: dict[str, ProviderProfile] = {
    p.id: p
    for p in (
        ProviderProfile(
            id="openrouter",
            label="OpenRouter",
            auth_type="api_key",
            api_mode="chat_completions",
            auth_header_type="bearer",
            key_required=True,
            base_url="https://openrouter.ai/api/v1",
            base_url_env_var="OPENROUTER_BASE_URL",
            api_key_env_vars=("OPENROUTER_API_KEY",),
            optional_metadata_env_vars=("OPENROUTER_SITE_URL", "OPENROUTER_SITE_NAME"),
            aliases=("or",),
            models=_OPENROUTER_MODELS,
            default_model="anthropic/claude-sonnet-4.6",
            docs_url="https://openrouter.ai/docs",
        ),
        ProviderProfile(
            id="openai",
            label="OpenAI",
            auth_type="api_key",
            api_mode="chat_completions",
            auth_header_type="bearer",
            key_required=True,
            base_url="https://api.openai.com/v1",
            base_url_env_var="OPENAI_BASE_URL",
            api_key_env_vars=("OPENAI_API_KEY",),
            aliases=(),
            models=_OPENAI_MODELS,
            default_model="gpt-5.5",
            docs_url="https://platform.openai.com/docs",
        ),
        ProviderProfile(
            id="anthropic",
            label="Anthropic",
            auth_type="api_key",
            api_mode="anthropic_messages",
            auth_header_type="x-api-key",
            key_required=True,
            base_url="https://api.anthropic.com",
            base_url_env_var="ANTHROPIC_BASE_URL",
            api_key_env_vars=("ANTHROPIC_API_KEY",),
            aliases=("claude",),
            models=_ANTHROPIC_MODELS,
            default_model="claude-sonnet-4.6",
            docs_url="https://docs.anthropic.com",
        ),
        ProviderProfile(
            id="deepseek",
            label="DeepSeek",
            auth_type="api_key",
            api_mode="chat_completions",
            auth_header_type="bearer",
            key_required=True,
            base_url="https://api.deepseek.com/v1",
            base_url_env_var="DEEPSEEK_BASE_URL",
            api_key_env_vars=("DEEPSEEK_API_KEY",),
            aliases=("ds",),
            models=_DEEPSEEK_MODELS,
            default_model="deepseek-v4-pro",
            docs_url="https://platform.deepseek.com/docs",
        ),
        ProviderProfile(
            id="kimi",
            label="Kimi / Moonshot",
            auth_type="api_key",
            api_mode="chat_completions",
            auth_header_type="bearer",
            key_required=True,
            base_url="https://api.moonshot.cn/v1",
            base_url_env_var="KIMI_BASE_URL",
            # MOONSHOT_API_KEY is canonical; KIMI_API_KEY is accepted alias
            api_key_env_vars=("MOONSHOT_API_KEY", "KIMI_API_KEY"),
            aliases=("moonshot",),
            models=_KIMI_MODELS,
            default_model="kimi-k2.6",
            docs_url="https://platform.moonshot.ai/docs",
        ),
        ProviderProfile(
            id="nvidia",
            label="NVIDIA NIM",
            auth_type="api_key",
            api_mode="chat_completions",
            auth_header_type="bearer",
            key_required=True,
            base_url="https://integrate.api.nvidia.com/v1",
            base_url_env_var="NVIDIA_BASE_URL",
            # NVIDIA_API_KEY for cloud/API Catalog inference.
            # NGC_API_KEY is NOT included here; it is for NGC/container workflows only.
            api_key_env_vars=("NVIDIA_API_KEY",),
            aliases=("nim",),
            models=_NVIDIA_MODELS,
            default_model="nvidia/nemotron-3-super-120b-a12b",
            docs_url="https://build.nvidia.com",
        ),
        ProviderProfile(
            id="xai",
            label="xAI",
            auth_type="api_key",
            api_mode="chat_completions",
            auth_header_type="bearer",
            key_required=True,
            base_url="https://api.x.ai/v1",
            base_url_env_var="XAI_BASE_URL",
            api_key_env_vars=("XAI_API_KEY",),
            aliases=("grok",),
            models=_XAI_MODELS,
            default_model="grok-4",
            docs_url="https://docs.x.ai",
        ),
        ProviderProfile(
            id="google-gemini",
            label="Google Gemini",
            auth_type="api_key",
            api_mode="chat_completions",
            auth_header_type="bearer",
            key_required=True,
            base_url="https://generativelanguage.googleapis.com/v1beta",
            base_url_env_var="GOOGLE_GEMINI_BASE_URL",
            # GOOGLE_API_KEY takes precedence over GEMINI_API_KEY when both exist,
            # matching Google SDK behavior.
            api_key_env_vars=("GOOGLE_API_KEY", "GOOGLE_GEMINI_API_KEY", "GEMINI_API_KEY"),
            aliases=("gemini", "google"),
            models=_GOOGLE_MODELS,
            default_model="gemini-3.1-pro-preview",
            docs_url="https://ai.google.dev/gemini-api/docs",
        ),
        ProviderProfile(
            id="huggingface",
            label="Hugging Face",
            auth_type="api_key",
            api_mode="chat_completions",
            auth_header_type="bearer",
            key_required=True,
            base_url="https://api-inference.huggingface.co/v1",
            base_url_env_var="HF_BASE_URL",
            # HF_TOKEN is canonical; HUGGINGFACEHUB_API_TOKEN is legacy alias.
            api_key_env_vars=("HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN"),
            aliases=("hf",),
            models=_HF_MODELS,
            default_model="moonshotai/Kimi-K2.6",
            docs_url="https://huggingface.co/docs/api-inference",
        ),
        ProviderProfile(
            id="local",
            label="Local / Self-hosted",
            auth_type="none",
            api_mode="chat_completions",
            auth_header_type="none",
            key_required=False,
            base_url="http://localhost:11434/v1",
            base_url_env_var="LOCAL_BASE_URL",
            api_key_env_vars=(),
            aliases=("ollama", "llamacpp"),
            models=_LOCAL_MODELS,
            default_model="local/default",
            docs_url="",
        ),
        ProviderProfile(
            id="custom",
            label="Custom / OpenAI-compatible",
            auth_type="api_key",
            api_mode="chat_completions",
            auth_header_type="bearer",
            key_required=True,
            base_url="",
            base_url_env_var="CUSTOM_BASE_URL",
            api_key_env_vars=("ATLAS_CUSTOM_API_KEY",),
            aliases=(),
            models=_CUSTOM_MODELS,
            default_model="custom",
            docs_url="",
        ),
    )
}

# Build alias -> canonical id mapping
_ALIAS_MAP: dict[str, str] = {}
for _profile in _PROVIDER_PROFILES.values():
    for _alias in _profile.aliases:
        _ALIAS_MAP[_alias] = _profile.id


def list_provider_profiles() -> list[ProviderProfile]:
    """Return all registered provider profiles, sorted by label."""
    return sorted(_PROVIDER_PROFILES.values(), key=lambda p: p.label.lower())


def get_provider_profile(provider_id_or_alias: str) -> ProviderProfile | None:
    """Look up a provider by canonical ID or alias."""
    key = provider_id_or_alias.lower().strip()
    if key in _PROVIDER_PROFILES:
        return _PROVIDER_PROFILES[key]
    canonical = _ALIAS_MAP.get(key)
    if canonical:
        return _PROVIDER_PROFILES.get(canonical)
    return None


def normalize_provider_id(provider_id_or_alias: str) -> str:
    """Return the canonical provider ID, or the input unchanged if unknown."""
    profile = get_provider_profile(provider_id_or_alias)
    return profile.id if profile else provider_id_or_alias.lower().strip()


def provider_model_ids(provider_id: str) -> list[str]:
    """Return model IDs for a given canonical provider ID."""
    profile = get_provider_profile(provider_id)
    if not profile:
        return []
    return [m.id for m in profile.models]


def default_model_for_provider(provider_id: str) -> str:
    """Return the default model for a provider, or empty string."""
    profile = get_provider_profile(provider_id)
    return profile.default_model if profile else ""


def is_known_model_for_provider(provider_id: str, model_id: str) -> bool:
    """Check whether a model ID is in the curated catalog for a provider."""
    return model_id in provider_model_ids(provider_id)
