"""Report models for local daily/weekly/ad-hoc report generation.

Reports use only local data. No provider calls, no broker calls, no network.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass
class ReportMetadata:
    report_type: Literal["daily", "weekly", "ad-hoc"]
    generated_at: str
    format: Literal["markdown", "json"]
    version: str = "1.0.0"
    workspace: str = "."


@dataclass
class PortfolioSummary:
    available: bool
    cash: float | None = None
    equity: float | None = None
    positions_count: int | None = None
    positions: list[dict[str, Any]] = field(default_factory=list)
    symbol: str | None = None


@dataclass
class BacktestSummary:
    available: bool
    recent_count: int = 0
    latest_run_id: str | None = None
    latest_symbol: str | None = None
    latest_return_pct: float | None = None
    latest_status: str | None = None
    total_runs: int = 0
    latest_schema_version: str | None = None
    latest_validation_status: str | None = None


@dataclass
class ResearchSummary:
    available: bool
    artifact_count: int = 0
    recent_evaluations: int = 0
    recent_plans: int = 0
    recent_verifications: int = 0
    symbol: str | None = None


@dataclass
class RiskSummary:
    available: bool
    live_trading_enabled: bool = False
    live_submit_enabled: bool = False
    kill_switch_enabled: bool = False
    max_daily_loss: float | None = None
    max_position_notional: float | None = None
    max_trades_per_day: int | None = None
    allow_leverage: bool = False


@dataclass
class AuditDecisionSummary:
    available: bool
    recent_events: int = 0
    recent_risk_approved: int = 0
    recent_risk_rejected: int = 0
    recent_backtest_completed: int = 0
    recent_backtest_failed: int = 0


@dataclass
class SystemHealthSummary:
    available: bool
    workspace_initialized: bool = False
    config_readable: bool = False
    ready_for_backtesting: bool = False
    ready_for_paper_agentic: bool = False
    ready_for_live: bool | str = False
    checks: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class MissingDataSection:
    missing_sources: list[str] = field(default_factory=list)


@dataclass
class ReportData:
    metadata: ReportMetadata
    portfolio: PortfolioSummary
    backtest: BacktestSummary
    research: ResearchSummary
    risk: RiskSummary
    audit_decisions: AuditDecisionSummary
    system_health: SystemHealthSummary
    missing_data: MissingDataSection
    disclaimer: str = ""


_DISCLAIMER = (
    "This report is generated from local, offline data only. "
    "It is a research/paper summary, not investment advice, not a prediction, "
    "and not a performance guarantee. No real trades were executed unless "
    "explicitly noted in audit logs. No provider or broker APIs were called "
    "during report generation."
)
