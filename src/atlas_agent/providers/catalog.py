from __future__ import annotations

from dataclasses import dataclass, field
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
    display_name: str
    status: str  # "stable", "beta", "local", "legacy", "internal"
    api_mode: str
    base_url: str
    base_url_required: bool
    model_required: bool
    key_required: bool
    canonical_env_var: str
    accepted_env_aliases: tuple[str, ...] = ()
    env_precedence: tuple[str, ...] = ()
    auth_header_type: str = "bearer"  # "bearer", "x-api-key", "x-goog-api-key", "none"
    required_headers: dict[str, str] = field(default_factory=dict)
    optional_metadata_env_vars: tuple[str, ...] = ()
    user_facing: bool = True
    include_in_wizard: bool = True
    include_in_model_providers_default: bool = True
    aliases: tuple[str, ...] = ()
    models: tuple[ModelOption, ...] = ()
    default_model: str = ""
    docs_url: str = ""
    
    @property
    def label(self) -> str:
        return self.display_name


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

_LMSTUDIO_MODELS = (
    ModelOption("local-model", label="Local Model"),
)

_OPENAI_COMPATIBLE_MODELS = (
    ModelOption("custom-model", label="Custom Model"),
)

_CUSTOM_MODELS = (
    ModelOption("custom", label="Custom"),
)

GOOGLE_PROVIDER_ID = "google"
GOOGLE_NATIVE_PROVIDER_ALIASES: tuple[str, ...] = (
    "google",
    "gemini",
    "google-gemini",
    "google-gemini-native",
)
GOOGLE_OPENAI_COMPATIBLE_PROVIDER_ALIASES: tuple[str, ...] = (
    "gemini-openai-compatible",
    "google-gemini-openai",
    "google-gemini-openai-compatible",
)

_PROVIDER_PROFILES: dict[str, ProviderProfile] = {
    p.id: p
    for p in (
        ProviderProfile(
            id="openrouter",
            display_name="OpenRouter",
            status="stable",
            api_mode="chat_completions",
            base_url="https://openrouter.ai/api/v1",
            base_url_required=False,
            model_required=True,
            key_required=True,
            canonical_env_var="OPENROUTER_API_KEY",
            accepted_env_aliases=(),
            env_precedence=("OPENROUTER_API_KEY",),
            auth_header_type="bearer",
            optional_metadata_env_vars=("OPENROUTER_HTTP_REFERER", "OPENROUTER_APP_TITLE"),
            aliases=("or",),
            models=_OPENROUTER_MODELS,
            default_model="anthropic/claude-sonnet-4.6",
            docs_url="https://openrouter.ai/docs",
        ),
        ProviderProfile(
            id="openai",
            display_name="OpenAI",
            status="stable",
            api_mode="chat_completions",
            base_url="https://api.openai.com/v1",
            base_url_required=False,
            model_required=True,
            key_required=True,
            canonical_env_var="OPENAI_API_KEY",
            accepted_env_aliases=(),
            env_precedence=("OPENAI_API_KEY",),
            auth_header_type="bearer",
            aliases=(),
            models=_OPENAI_MODELS,
            default_model="gpt-5.5",
            docs_url="https://platform.openai.com/docs",
        ),
        ProviderProfile(
            id="anthropic",
            display_name="Anthropic",
            status="stable",
            api_mode="anthropic_messages",
            base_url="https://api.anthropic.com",
            base_url_required=False,
            model_required=True,
            key_required=True,
            canonical_env_var="ANTHROPIC_API_KEY",
            accepted_env_aliases=(),
            env_precedence=("ANTHROPIC_API_KEY",),
            auth_header_type="x-api-key",
            required_headers={"anthropic-version": "2023-06-01", "content-type": "application/json"},
            aliases=("claude",),
            models=_ANTHROPIC_MODELS,
            default_model="claude-sonnet-4.6",
            docs_url="https://docs.anthropic.com",
        ),
        ProviderProfile(
            id="deepseek",
            display_name="DeepSeek",
            status="stable",
            api_mode="chat_completions",
            base_url="https://api.deepseek.com",
            base_url_required=False,
            model_required=True,
            key_required=True,
            canonical_env_var="DEEPSEEK_API_KEY",
            accepted_env_aliases=(),
            env_precedence=("DEEPSEEK_API_KEY",),
            auth_header_type="bearer",
            aliases=("ds",),
            models=_DEEPSEEK_MODELS,
            default_model="deepseek-v4-pro",
            docs_url="https://platform.deepseek.com/docs",
        ),
        ProviderProfile(
            id="kimi",
            display_name="Kimi / Moonshot",
            status="stable",
            api_mode="chat_completions",
            base_url="https://api.moonshot.cn/v1",
            base_url_required=False,
            model_required=True,
            key_required=True,
            canonical_env_var="MOONSHOT_API_KEY",
            accepted_env_aliases=("KIMI_API_KEY",),
            env_precedence=("MOONSHOT_API_KEY", "KIMI_API_KEY"),
            auth_header_type="bearer",
            aliases=("moonshot",),
            models=_KIMI_MODELS,
            default_model="kimi-k2.6",
            docs_url="https://platform.moonshot.ai/docs",
        ),
        ProviderProfile(
            id=GOOGLE_PROVIDER_ID,
            display_name="Google Gemini",
            status="stable",
            api_mode="gemini_native",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            base_url_required=False,
            model_required=True,
            key_required=True,
            canonical_env_var="GOOGLE_API_KEY",
            accepted_env_aliases=("GEMINI_API_KEY",),
            env_precedence=("GOOGLE_API_KEY", "GEMINI_API_KEY"),
            auth_header_type="x-goog-api-key",
            aliases=GOOGLE_NATIVE_PROVIDER_ALIASES + GOOGLE_OPENAI_COMPATIBLE_PROVIDER_ALIASES,
            models=_GOOGLE_MODELS,
            default_model="gemini-3.1-pro-preview",
            docs_url="https://ai.google.dev/gemini-api/docs",
        ),
        ProviderProfile(
            id="xai",
            display_name="xAI",
            status="stable",
            api_mode="chat_completions",
            base_url="https://api.x.ai/v1",
            base_url_required=False,
            model_required=True,
            key_required=True,
            canonical_env_var="XAI_API_KEY",
            accepted_env_aliases=(),
            env_precedence=("XAI_API_KEY",),
            auth_header_type="bearer",
            aliases=("grok",),
            models=_XAI_MODELS,
            default_model="grok-4",
            docs_url="https://docs.x.ai",
        ),
        ProviderProfile(
            id="huggingface",
            display_name="Hugging Face",
            status="stable",
            api_mode="chat_completions",
            base_url="https://api-inference.huggingface.co/v1",
            base_url_required=False,
            model_required=True,
            key_required=True,
            canonical_env_var="HF_TOKEN",
            accepted_env_aliases=("HUGGINGFACEHUB_API_TOKEN",),
            env_precedence=("HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN"),
            auth_header_type="bearer",
            aliases=("hf",),
            models=_HF_MODELS,
            default_model="moonshotai/Kimi-K2.6",
            docs_url="https://huggingface.co/docs/api-inference",
        ),
        ProviderProfile(
            id="local",
            display_name="Local / Self-hosted",
            status="local",
            api_mode="chat_completions",
            base_url="http://localhost:11434/v1",
            base_url_required=False,
            model_required=False,
            key_required=False,
            canonical_env_var="",
            accepted_env_aliases=(),
            env_precedence=(),
            auth_header_type="none",
            aliases=("ollama", "llamacpp"),
            models=_LOCAL_MODELS,
            default_model="local/default",
            docs_url="",
        ),
        ProviderProfile(
            id="nvidia",
            display_name="NVIDIA NIM (Cloud)",
            status="stable",
            api_mode="chat_completions",
            base_url="https://integrate.api.nvidia.com/v1",
            base_url_required=False,
            model_required=True,
            key_required=True,
            canonical_env_var="NVIDIA_API_KEY",
            accepted_env_aliases=(),
            env_precedence=("NVIDIA_API_KEY",),
            auth_header_type="bearer",
            aliases=("nim",),
            models=_NVIDIA_MODELS,
            default_model="nvidia/nemotron-3-super-120b-a12b",
            docs_url="https://build.nvidia.com",
        ),
        ProviderProfile(
            id="nvidia-local",
            display_name="NVIDIA NIM (Local/On-Prem)",
            status="local",
            api_mode="chat_completions",
            base_url="",
            base_url_required=True,
            model_required=True,
            key_required=False,
            canonical_env_var="NVIDIA_LOCAL_API_KEY",
            accepted_env_aliases=(),
            env_precedence=("NVIDIA_LOCAL_API_KEY",),
            auth_header_type="none",
            aliases=("nvidia-nim-local",),
            models=_NVIDIA_MODELS,
            default_model="nvidia/nemotron-3-super-120b-a12b",
            docs_url="https://build.nvidia.com",
        ),
        ProviderProfile(
            id="lmstudio",
            display_name="LM Studio",
            status="local",
            api_mode="chat_completions",
            base_url="http://localhost:1234/v1",
            base_url_required=False,
            model_required=False,
            key_required=False,
            canonical_env_var="",
            accepted_env_aliases=(),
            env_precedence=(),
            auth_header_type="none",
            aliases=("lm-studio",),
            models=_LMSTUDIO_MODELS,
            default_model="local-model",
            docs_url="https://lmstudio.ai/docs",
        ),
        ProviderProfile(
            id="openai-compatible",
            display_name="OpenAI-compatible Endpoint",
            status="stable",
            api_mode="chat_completions",
            base_url="",
            base_url_required=True,
            model_required=True,
            key_required=False,
            canonical_env_var="ATLAS_OPENAI_COMPATIBLE_API_KEY",
            accepted_env_aliases=(),
            env_precedence=("ATLAS_OPENAI_COMPATIBLE_API_KEY",),
            auth_header_type="bearer",
            aliases=("openai_compatible",),
            models=_OPENAI_COMPATIBLE_MODELS,
            default_model="custom-model",
            docs_url="",
        ),
        ProviderProfile(
            id="custom",
            display_name="Custom Endpoint",
            status="stable",
            api_mode="chat_completions",
            base_url="",
            base_url_required=True,
            model_required=True,
            key_required=False,
            canonical_env_var="ATLAS_CUSTOM_API_KEY",
            accepted_env_aliases=(),
            env_precedence=("ATLAS_CUSTOM_API_KEY",),
            auth_header_type="bearer",
            aliases=(),
            models=_CUSTOM_MODELS,
            default_model="custom",
            docs_url="",
        ),
        ProviderProfile(
            id="local_command",
            display_name="Local Command (Legacy)",
            status="legacy",
            api_mode="custom",
            base_url="",
            base_url_required=False,
            model_required=False,
            key_required=False,
            canonical_env_var="",
            accepted_env_aliases=(),
            env_precedence=(),
            auth_header_type="none",
            user_facing=False,
            include_in_wizard=False,
            include_in_model_providers_default=False,
            aliases=(),
            models=(),
            default_model="local_command",
            docs_url="",
        ),
        ProviderProfile(
            id="null",
            display_name="Null Provider",
            status="internal",
            api_mode="custom",
            base_url="",
            base_url_required=False,
            model_required=False,
            key_required=False,
            canonical_env_var="",
            accepted_env_aliases=(),
            env_precedence=(),
            auth_header_type="none",
            user_facing=False,
            include_in_wizard=False,
            include_in_model_providers_default=False,
            aliases=(),
            models=(),
            default_model="null",
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
    return sorted(_PROVIDER_PROFILES.values(), key=lambda p: p.display_name.lower())


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


def is_google_provider_id(provider_id_or_alias: str) -> bool:
    """Return True when a provider id/alias resolves to canonical Google Gemini."""
    return normalize_provider_id(provider_id_or_alias) == GOOGLE_PROVIDER_ID


def infer_google_api_mode(provider_id_or_alias: str) -> str | None:
    """Infer google mode from a legacy provider id/alias, if present."""
    key = provider_id_or_alias.lower().strip()
    if key in GOOGLE_OPENAI_COMPATIBLE_PROVIDER_ALIASES:
        return "openai_compatible"
    if key in GOOGLE_NATIVE_PROVIDER_ALIASES:
        return "native"
    return None


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
