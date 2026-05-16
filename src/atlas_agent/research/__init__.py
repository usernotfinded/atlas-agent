import os

from atlas_agent.research.perplexity import (
    PerplexityResearchProvider,
    ResearchConfigurationError,
)
from atlas_agent.research.research_report import ResearchReport
from atlas_agent.research.session import (
    ResearchArtifact,
    ResearchSessionError,
    run_research_session,
    sanitize_symbol,
)
from atlas_agent.research.web_research import OfflineResearchProvider


def get_research_provider() -> PerplexityResearchProvider | OfflineResearchProvider:
    """Return the configured research provider based on environment variables."""
    if os.getenv("ATLAS_RESEARCH_API_KEY") or os.getenv("RESEARCH_API_KEY") or os.getenv("PERPLEXITY_API_KEY"):
        return PerplexityResearchProvider()
    return OfflineResearchProvider()


__all__ = [
    "OfflineResearchProvider",
    "PerplexityResearchProvider",
    "ResearchArtifact",
    "ResearchConfigurationError",
    "ResearchReport",
    "ResearchSessionError",
    "get_research_provider",
    "run_research_session",
    "sanitize_symbol",
]

