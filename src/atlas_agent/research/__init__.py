# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    research/__init__.py
# PURPOSE: Public surface of the research domain.
# DEPS:    research.session, research.perplexity, research.artifact_store
#
# THE SHAPE OF THIS PACKAGE
# -------------------------
# research/ is the project's OUTBOUND data boundary: the one place where the
# workspace's contents can leave the machine for a third-party provider. Almost
# every `provider_*` module here is a link in an EVIDENCE CHAIN whose job is to make
# that crossing provable rather than to make it happen:
#
#   call_plan            → what we would send
#   preflight_freeze     → pinned, so it cannot change after review
#   credential_boundary  → which secrets are in scope (and that none are in the artifact)
#   opt_in_policy        → the explicit consent
#   outbound_payload_preview → the exact bytes, readable by a human
#   execution_state / unlock_state → the gate, and whether it is open
#   dry_run              → run everything except the send
#   readiness_report / audit_packet → the sealed record
#   response_* / mock_response_* → the response is untrusted input, validated
#                          against a closed schema and reviewed before it is believed
#   safety_dossier       → the assembled proof
#
# Every one of them is local-only, configless and network-free. That is not a style
# choice: a module that could itself make the provider call would be able to
# manufacture the very evidence it exists to produce.
# ==============================================================================

# --- IMPORTS ---
import os

from atlas_agent.research.perplexity import (
    PerplexityResearchProvider,
    ResearchConfigurationError,
)
from atlas_agent.research.providers import (
    ResearchContext,
    ResearchProvider,
    ResearchProviderInfo,
    ResearchProviderResult,
    list_research_providers,
    resolve_research_provider,
)
from atlas_agent.research.research_report import ResearchReport
from atlas_agent.research.session import (
    DeterministicResearchProvider,
    EvaluationArtifact,
    PaperPlanArtifact,
    RESEARCH_ARTIFACT_SCHEMA_VERSION,
    ResearchArtifact,
    ResearchSessionError,
    SUPPORTED_RESEARCH_PROVIDERS,
    UnsupportedArtifactSchemaError,
    UnsupportedResearchProviderError,
    build_research_timeline,
    check_research_artifacts,
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
    "RESEARCH_ARTIFACT_SCHEMA_VERSION",
    "ResearchArtifact",
    "ResearchConfigurationError",
    "ResearchContext",
    "ResearchProvider",
    "ResearchProviderInfo",
    "ResearchProviderResult",
    "ResearchReport",
    "list_research_providers",
    "ResearchSessionError",
    "SUPPORTED_RESEARCH_PROVIDERS",
    "UnsupportedArtifactSchemaError",
    "UnsupportedResearchProviderError",
    "build_research_timeline",
    "check_research_artifacts",
    "create_paper_plan",
    "evaluate_paper_plan",
    "find_research_artifact_by_run_id",
    "get_research_provider",
    "iter_research_artifacts",
    "load_research_artifact",
    "resolve_research_provider",
    "run_research_session",
    "sanitize_symbol",
    "validate_run_id",
]

