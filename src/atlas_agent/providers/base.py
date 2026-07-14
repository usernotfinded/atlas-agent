# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    providers/base.py
# PURPOSE: The contract every LLM provider satisfies. One interface over OpenAI,
#          Anthropic, OpenRouter and local models, so the agent never learns which
#          vendor it is talking to — and swapping one out changes no business logic.
# DEPS:    tools.spec (LLMResponse, ToolDescription, ModelCapabilities)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol

from atlas_agent.tools.spec import LLMResponse, ModelCapabilities, ToolDescription


# ==============================================================================
# REQUEST / RESPONSE MODELS
# ==============================================================================

@dataclass(frozen=True)
class ProviderRequest:
    system_prompt: str
    user_prompt: str
    model: str
    # 0.0 by default. Trading decisions must be reproducible from their inputs: a
    # non-deterministic model makes the audit trail unfalsifiable, because the same
    # context could have produced a different trade.
    temperature: float = 0.0
    max_tokens: int = 1_000
    context_files: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    parsed_json: dict[str, Any] | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    # Kept for the audit trail, NOT for business logic. Nothing downstream may branch
    # on a vendor-shaped payload, or the abstraction this file exists to provide is
    # gone.
    raw_response: Any = None
    finish_reason: str = "stop"


# ==============================================================================
# PROVIDER CONTRACT
# ==============================================================================

class AIProvider(Protocol):
    def complete(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[ToolDescription],
        model: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        ...

    def summarize(
        self,
        text: str,
        max_tokens: int,
    ) -> str:
        ...

    def capabilities(self) -> ModelCapabilities:
        ...

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        ...


# ==============================================================================
# SHARED BASE IMPLEMENTATION
# ==============================================================================

# Only two abstract methods. Everything else — summarize() below — is derived from
# them, so a new adapter has the smallest possible amount of code that can be wrong.
class BaseAIProvider(ABC):
    @abstractmethod
    def complete(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[ToolDescription],
        model: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        ...

    @abstractmethod
    def capabilities(self) -> ModelCapabilities:
        ...

    # Implemented once, in terms of complete(), rather than per-vendor. Every adapter
    # inheriting the same summarisation prompt is what keeps summaries comparable
    # across providers.
    def summarize(
        self,
        text: str,
        max_tokens: int,
    ) -> str:
        response = self.complete(
            system_prompt=(
                "You are a concise summarization assistant. "
                "Return plain text only."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Summarize the following text in at most "
                        f"{max_tokens} tokens.\n\n{text}"
                    ),
                }
            ],
            tools=[],
            model=self.capabilities().model_name,
            temperature=0.0,
        )
        return (response.text or "").strip()


class ProviderConfigurationError(RuntimeError):
    pass
