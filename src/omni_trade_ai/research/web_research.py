from __future__ import annotations

from omni_trade_ai.research.research_report import ResearchReport


class OfflineResearchProvider:
    def research_market(self, symbol: str) -> ResearchReport:
        return ResearchReport(
            symbol=symbol.upper(),
            provider="offline",
            summary="No research provider configured; using local strategy context only.",
        )

