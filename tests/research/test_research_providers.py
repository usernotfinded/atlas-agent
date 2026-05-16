from __future__ import annotations

import pytest

from atlas_agent.research.providers import (
    DisabledLLMResearchProvider,
    ResearchContext,
    ResearchProviderResult,
    UnsupportedResearchProviderError,
    resolve_research_provider,
)
from atlas_agent.research.session import DeterministicResearchProvider


class TestResearchContext:
    def test_default_mode_is_paper(self) -> None:
        ctx = ResearchContext(symbol="AAPL")
        assert ctx.symbol == "AAPL"
        assert ctx.mode == "paper"

    def test_custom_mode(self) -> None:
        ctx = ResearchContext(symbol="TSLA", mode="analysis")
        assert ctx.mode == "analysis"


class TestResearchProviderResult:
    def test_defaults(self) -> None:
        result = ResearchProviderResult(provider="test", summary="summary")
        assert result.provider == "test"
        assert result.summary == "summary"
        assert result.thesis == ""
        assert result.market_context == ""
        assert result.risks == []
        assert result.invalidation_conditions == []
        assert result.paper_only_plan == ""
        assert result.citations == []
        assert result.warnings == []
        assert result.metadata == {}

    def test_frozen(self) -> None:
        result = ResearchProviderResult(provider="test", summary="summary")
        with pytest.raises(AttributeError):
            result.provider = "other"  # type: ignore[misc]


class TestDeterministicResearchProvider:
    def test_name(self) -> None:
        provider = DeterministicResearchProvider()
        assert provider.name == "deterministic"

    def test_generate_research(self) -> None:
        provider = DeterministicResearchProvider()
        ctx = ResearchContext(symbol="AAPL")
        result = provider.generate_research("AAPL", ctx)
        assert result.provider == "deterministic"
        assert "AAPL" in result.summary
        assert result.thesis
        assert result.market_context
        assert len(result.risks) > 0
        assert len(result.invalidation_conditions) > 0
        assert result.paper_only_plan
        assert result.metadata["source"] == "deterministic"

    def test_generate_research_uppercases_symbol(self) -> None:
        provider = DeterministicResearchProvider()
        ctx = ResearchContext(symbol="aapl")
        result = provider.generate_research("aapl", ctx)
        assert "AAPL" in result.summary

    def test_no_network_call(self) -> None:
        provider = DeterministicResearchProvider()
        ctx = ResearchContext(symbol="AAPL")
        result = provider.generate_research("AAPL", ctx)
        assert "No external data queried" in result.summary


class TestDisabledLLMResearchProvider:
    def test_name(self) -> None:
        provider = DisabledLLMResearchProvider()
        assert provider.name == "llm_disabled"

    def test_always_raises(self) -> None:
        provider = DisabledLLMResearchProvider()
        ctx = ResearchContext(symbol="AAPL")
        with pytest.raises(UnsupportedResearchProviderError, match="Unsupported research provider"):
            provider.generate_research("AAPL", ctx)


class TestResolveResearchProvider:
    def test_none_returns_deterministic(self) -> None:
        provider = resolve_research_provider(None)
        assert isinstance(provider, DeterministicResearchProvider)

    def test_deterministic_returns_deterministic(self) -> None:
        provider = resolve_research_provider("deterministic")
        assert isinstance(provider, DeterministicResearchProvider)

    def test_unsupported_raises(self) -> None:
        with pytest.raises(UnsupportedResearchProviderError, match="Unsupported research provider"):
            resolve_research_provider("openai")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(UnsupportedResearchProviderError, match="Unsupported research provider"):
            resolve_research_provider("")
