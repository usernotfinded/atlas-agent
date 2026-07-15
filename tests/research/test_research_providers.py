# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/research/test_research_providers.py
# PURPOSE: Verifies research providers behavior and regression expectations.
# DEPS:    inspect, pathlib, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from atlas_agent.research.providers import (
    DisabledLLMResearchProvider,
    ResearchContext,
    ResearchProviderResult,
    UnsupportedResearchProviderError,
    resolve_research_provider,
)
from atlas_agent.research.session import DeterministicResearchProvider


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

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

    def test_secret_like_name_does_not_leak(self) -> None:
        with pytest.raises(UnsupportedResearchProviderError) as exc_info:
            resolve_research_provider("sk-LEAKEDSECRET123456")
        msg = str(exc_info.value)
        assert "sk-LEAKEDSECRET123456" not in msg
        assert "Unsupported research provider" in msg

    def test_no_silent_fallback(self) -> None:
        with pytest.raises(UnsupportedResearchProviderError):
            resolve_research_provider("openai")


class TestProviderCodeStatic:
    """Static analysis of provider source code — no network/LLM SDK imports."""

    PROVIDERS_PATH = Path(__file__).resolve().parents[2] / "src" / "atlas_agent" / "research" / "providers.py"

    def _source(self) -> str:
        return self.PROVIDERS_PATH.read_text(encoding="utf-8")

    def test_no_openai_import(self) -> None:
        src = self._source()
        assert "openai" not in src.lower()

    def test_no_anthropic_import(self) -> None:
        src = self._source()
        assert "anthropic" not in src.lower()

    def test_no_google_generativeai_import(self) -> None:
        src = self._source()
        assert "google.generativeai" not in src.lower()
        assert "genai" not in src.lower()

    def test_no_requests_import(self) -> None:
        src = self._source()
        assert "import requests" not in src
        assert "from requests" not in src

    def test_no_httpx_import(self) -> None:
        src = self._source()
        assert "import httpx" not in src
        assert "from httpx" not in src

    def test_no_urllib_request_import(self) -> None:
        src = self._source()
        assert "urllib.request" not in src

    def test_no_api_key_reads(self) -> None:
        src = self._source()
        lower = src.lower()
        # "requires_api_key" is an allowed metadata field name
        assert "getenv" not in lower
        assert "environ" not in lower
        assert "os.getenv" not in lower
        assert "os.environ" not in lower

    def test_generate_research_has_no_network_calls(self) -> None:
        """Inspect generate_research methods for banned call patterns."""
        src = self._source()
        banned = ["requests.get", "requests.post", "httpx.get", "httpx.post", "urllib.request.urlopen"]
        for call in banned:
            assert call not in src, f"Banned network call pattern found: {call}"
