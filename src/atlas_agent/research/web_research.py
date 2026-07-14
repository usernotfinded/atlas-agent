# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    research/web_research.py
# PURPOSE: Compatibility re-export for the research report type.
# DEPS:    research.research_report
# ==============================================================================

from __future__ import annotations

from atlas_agent.research.research_report import ResearchReport


class OfflineResearchProvider:
    def research_market(self, symbol: str) -> ResearchReport:
        return ResearchReport(
            symbol=symbol.upper(),
            provider="offline",
            summary="No research provider configured; using local strategy context only.",
        )

