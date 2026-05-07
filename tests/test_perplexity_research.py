from __future__ import annotations

import pytest

from atlas_agent.research.perplexity import (
    PerplexityResearchProvider,
    ResearchConfigurationError,
)


def test_perplexity_wrapper_fails_safely_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

    with pytest.raises(ResearchConfigurationError, match="PERPLEXITY_API_KEY"):
        PerplexityResearchProvider().research_market("SPY")


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
