from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


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
    def generate(self, request: ProviderRequest) -> ProviderResponse:
        ...


class ProviderConfigurationError(RuntimeError):
    pass

