# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    dashboard/models.py
# PURPOSE: The shape of a dashboard snapshot — one section per domain (portfolio,
#          safety, audit, learning, ...).
# DEPS:    pydantic (models)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, List, Literal, Optional
from pydantic import BaseModel, Field


# ==============================================================================
# SNAPSHOT SECTIONS
# ==============================================================================

class DashboardStatusSummary(BaseModel):
    status: str
    message: Optional[str] = None
    last_updated: Optional[str] = None


class DashboardSystemHealth(BaseModel):
    available: bool = False
    workspace_initialized: bool = False
    config_readable: bool = False
    ready_for_backtesting: bool = False
    ready_for_paper_agentic: bool = False
    ready_for_live: bool | str = False
    checks: list[dict[str, Any]] = Field(default_factory=list)


class DashboardPortfolio(BaseModel):
    available: bool = False
    cash: float | None = None
    equity: float | None = None
    positions_count: int = 0
    symbol: str | None = None


class DashboardBacktests(BaseModel):
    available: bool = False
    total_runs: int = 0
    recent_count: int = 0
    latest_run_id: str | None = None
    latest_symbol: str | None = None
    latest_return_pct: float | None = None
    latest_status: str | None = None
    latest_schema_version: str | None = None
    latest_validation_status: str | None = None


class DashboardReports(BaseModel):
    available: bool = False
    report_count: int = 0
    latest_report_type: str | None = None
    latest_generated_at: str | None = None


class DashboardReflections(BaseModel):
    available: bool = False
    total_count: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)


class DashboardSkills(BaseModel):
    available: bool = False
    candidate_count: int = 0
    library_count: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)


class DashboardLearning(BaseModel):
    available: bool = False
    suggestion_count: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)


class DashboardAudit(BaseModel):
    available: bool = False
    recent_events: int = 0
    recent_risk_approved: int = 0
    recent_risk_rejected: int = 0
    recent_backtest_completed: int = 0
    recent_backtest_failed: int = 0


class DashboardSafety(BaseModel):
    available: bool = False
    kill_switch_mode: str = "normal"
    kill_switch_active: bool = False
    heartbeat_status: str = "unknown"
    live_trading_enabled: bool = False
    live_submit_enabled: bool = False


class DashboardSnapshot(BaseModel):
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    workspace: str
    mode: Literal["paper", "live", "unknown"] = "unknown"
    dashboard_mode: str = "read_only"
    configured: bool = False

    provider_summary: DashboardStatusSummary = Field(default_factory=lambda: DashboardStatusSummary(status="unknown"))
    broker_sync_summary: DashboardStatusSummary = Field(default_factory=lambda: DashboardStatusSummary(status="unknown"))
    portfolio_summary: dict[str, Any] = Field(default_factory=dict)
    open_orders_summary: dict[str, Any] = Field(default_factory=dict)
    risk_summary: DashboardStatusSummary = Field(default_factory=lambda: DashboardStatusSummary(status="unknown"))
    kill_switch_summary: dict[str, Any] = Field(default_factory=dict)
    heartbeat_summary: DashboardStatusSummary = Field(default_factory=lambda: DashboardStatusSummary(status="unknown"))
    audit_summary: dict[str, Any] = Field(default_factory=dict)
    safety_plan_summary: dict[str, Any] = Field(default_factory=dict)

    recent_events: List[dict[str, Any]] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)

    # New data-layer view models
    system_health: DashboardSystemHealth = Field(default_factory=DashboardSystemHealth)
    portfolio: DashboardPortfolio = Field(default_factory=DashboardPortfolio)
    backtests: DashboardBacktests = Field(default_factory=DashboardBacktests)
    reports: DashboardReports = Field(default_factory=DashboardReports)
    reflections: DashboardReflections = Field(default_factory=DashboardReflections)
    skills: DashboardSkills = Field(default_factory=DashboardSkills)
    learning: DashboardLearning = Field(default_factory=DashboardLearning)
    audit: DashboardAudit = Field(default_factory=DashboardAudit)
    safety: DashboardSafety = Field(default_factory=DashboardSafety)
    warnings: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
