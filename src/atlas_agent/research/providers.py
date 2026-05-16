from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class UnsupportedResearchProviderError(RuntimeError):
    """Raised when a research provider name is not supported."""


@dataclass(frozen=True)
class ResearchContext:
    """Safe context passed to a research provider. No secrets or broker data."""

    symbol: str
    mode: str = "paper"


@dataclass(frozen=True)
class ResearchProviderResult:
    """Result from a research provider. No raw credentials or broker bodies."""

    provider: str
    summary: str
    thesis: str = ""
    market_context: str = ""
    risks: list[str] = field(default_factory=list)
    invalidation_conditions: list[str] = field(default_factory=list)
    paper_only_plan: str = ""
    citations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)


class ResearchProvider(Protocol):
    """Protocol for research providers. No network calls required."""

    @property
    def name(self) -> str:
        ...

    def generate_research(self, symbol: str, context: ResearchContext) -> ResearchProviderResult:
        ...


class DisabledLLMResearchProvider:
    """Fail-closed stub for LLM providers.

    This provider is never enabled. It exists only as a typed placeholder
    so the interface layer is complete while external LLM support remains
    unimplemented and disabled.
    """

    @property
    def name(self) -> str:
        return "llm_disabled"

    def generate_research(self, symbol: str, context: ResearchContext) -> ResearchProviderResult:
        raise UnsupportedResearchProviderError("Unsupported research provider.")


def resolve_research_provider(name: str | None) -> ResearchProvider:
    """Return a research provider by name.

    Only 'deterministic' is enabled. All other names fail closed.
    """
    if name is None or name == "deterministic":
        # Lazy import to avoid circular dependency with session.py
        from atlas_agent.research.session import DeterministicResearchProvider

        return DeterministicResearchProvider()
    raise UnsupportedResearchProviderError("Unsupported research provider.")
