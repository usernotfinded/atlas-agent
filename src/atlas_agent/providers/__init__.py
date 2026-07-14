# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    providers/__init__.py
# PURPOSE: Public surface of the provider domain — the contracts, the adapters, and
#          NullProvider. Concrete vendor clients are reached through the factory, so
#          credential resolution is never bypassed by importing one directly.
# DEPS:    providers.base, providers.adapters, providers.null_provider
# ==============================================================================

# --- IMPORTS ---
from atlas_agent.providers.adapters import (
    AnthropicAdapter,
    JSONFallbackAdapter,
    OpenAICompatibleAdapter,
)
from atlas_agent.providers.base import AIProvider, BaseAIProvider, ProviderRequest, ProviderResponse
from atlas_agent.providers.null_provider import NullProvider


# ==============================================================================
# PUBLIC API
# ==============================================================================

__all__ = [
    "AIProvider",
    "BaseAIProvider",
    "NullProvider",
    "ProviderRequest",
    "ProviderResponse",
    "OpenAICompatibleAdapter",
    "AnthropicAdapter",
    "JSONFallbackAdapter",
]
