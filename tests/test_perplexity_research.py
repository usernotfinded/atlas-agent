# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_perplexity_research.py
# PURPOSE: Verifies perplexity research behavior and regression expectations.
# DEPS:    pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import pytest

from atlas_agent.research.perplexity import (
    PerplexityResearchProvider,
    ResearchConfigurationError,
)


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_perplexity_wrapper_fails_safely_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATLAS_RESEARCH_API_KEY", raising=False)
    monkeypatch.delenv("RESEARCH_API_KEY", raising=False)
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

    with pytest.raises(ResearchConfigurationError, match="ATLAS_RESEARCH_API_KEY"):
        PerplexityResearchProvider().research_market("SPY")


def test_perplexity_wrapper_uses_research_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_RESEARCH_API_KEY", "new-key")
    monkeypatch.delenv("RESEARCH_API_KEY", raising=False)
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    provider = PerplexityResearchProvider()
    assert provider.api_key == "new-key"


def test_perplexity_wrapper_uses_perplexity_api_key_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATLAS_RESEARCH_API_KEY", raising=False)
    monkeypatch.delenv("RESEARCH_API_KEY", raising=False)
    monkeypatch.setenv("PERPLEXITY_API_KEY", "legacy-key")
    provider = PerplexityResearchProvider()
    assert provider.api_key == "legacy-key"


def test_perplexity_wrapper_uses_mocked_http_without_printing_key() -> None:
    calls = []

    def fake_post(url, headers, payload):
        calls.append((url, headers, payload))
        return {
            "choices": [{"message": {"content": "SPY market context"}}],
            "citations": ["https://example.test"],
        }

    report = PerplexityResearchProvider(api_key="test-key", http_post=fake_post).research_market(
        "SPY"
    )

    assert report.summary == "SPY market context"
    assert report.citations == ("https://example.test",)
    assert calls[0][1]["Authorization"] == "Bearer " + "test-key"
