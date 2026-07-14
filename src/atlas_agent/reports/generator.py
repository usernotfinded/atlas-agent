# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    reports/generator.py
# PURPOSE: Assembles report data from local sources. Degrades to explicit "no data"
#          rather than to a plausible-looking empty report — a P&L report that
#          silently shows zero because the source was missing is a lie.
# DEPS:    reports.sources, reports.models
# ==============================================================================

"""Report generator for daily, weekly, and ad-hoc local reports.

Uses only local data sources. Safe when data is missing.
"""

# --- IMPORTS ---
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from atlas_agent.reports.models import (
    ReportData,
    ReportMetadata,
    _DISCLAIMER,
)
from atlas_agent.reports.sources import (
    collect_missing_data,
    load_audit_decision_summary,
    load_backtest_summary,
    load_portfolio_summary,
    load_research_summary,
    load_risk_summary,
    load_system_health_summary,
)


def generate_report(
    report_type: Literal["daily", "weekly", "ad-hoc"],
    workspace: str = ".",
    output_format: Literal["markdown", "json"] = "markdown",
) -> ReportData:
    """Generate a report from all available local data sources.

    Each section is safe if its source data is missing.
    """
    metadata = ReportMetadata(
        report_type=report_type,
        generated_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
        format=output_format,
        version="1.0.0",
        workspace=str(workspace),
    )

    portfolio = load_portfolio_summary(workspace)
    backtest = load_backtest_summary(workspace)
    research = load_research_summary(workspace)
    risk = load_risk_summary(workspace)
    audit = load_audit_decision_summary(workspace)
    system_health = load_system_health_summary(workspace)
    missing_data = collect_missing_data(portfolio, backtest, research, risk, audit, system_health)

    return ReportData(
        metadata=metadata,
        portfolio=portfolio,
        backtest=backtest,
        research=research,
        risk=risk,
        audit_decisions=audit,
        system_health=system_health,
        missing_data=missing_data,
        disclaimer=_DISCLAIMER,
    )
