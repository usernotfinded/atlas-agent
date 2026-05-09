from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol

from atlas_agent.tools.spec import LLMResponse, ModelCapabilities, ToolDescription


@dataclass(frozen=True)
class ProviderRequest:
    system_prompt: str
    user_prompt: str
    model: str
    temperature: float = 0.0
    max_tokens: int = 1_000
    context_files: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    parsed_json: dict[str, Any] | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    raw_response: Any = None
    finish_reason: str = "stop"


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
