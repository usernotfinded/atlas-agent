import os

from atlas_agent.research.perplexity import (
    PerplexityResearchProvider,
    ResearchConfigurationError,
)
from atlas_agent.research.research_report import ResearchReport
from atlas_agent.research.session import (
    DeterministicResearchProvider,
    EvaluationArtifact,
    PaperPlanArtifact,
    ResearchArtifact,
    ResearchSessionError,
    SUPPORTED_RESEARCH_PROVIDERS,
    UnsupportedResearchProviderError,
    create_paper_plan,
    evaluate_paper_plan,
    find_research_artifact_by_run_id,
    iter_research_artifacts,
    load_research_artifact,
    run_research_session,
    sanitize_symbol,
    validate_run_id,
)
from atlas_agent.research.web_research import OfflineResearchProvider


def get_research_provider() -> PerplexityResearchProvider | OfflineResearchProvider:
    """Return the configured research provider based on environment variables."""
    if os.getenv("ATLAS_RESEARCH_API_KEY") or os.getenv("RESEARCH_API_KEY") or os.getenv("PERPLEXITY_API_KEY"):
        return PerplexityResearchProvider()
    return OfflineResearchProvider()


__all__ = [
    "DeterministicResearchProvider",
    "EvaluationArtifact",
    "OfflineResearchProvider",
    "PaperPlanArtifact",
    "PerplexityResearchProvider",
    "ResearchArtifact",
    "ResearchConfigurationError",
    "ResearchReport",
    "ResearchSessionError",
    "SUPPORTED_RESEARCH_PROVIDERS",
    "UnsupportedResearchProviderError",
    "create_paper_plan",
    "evaluate_paper_plan",
    "find_research_artifact_by_run_id",
    "get_research_provider",
    "iter_research_artifacts",
    "load_research_artifact",
    "run_research_session",
    "sanitize_symbol",
    "validate_run_id",
]

