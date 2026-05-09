from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, List, Literal, Optional
from pydantic import BaseModel, Field


class DashboardStatusSummary(BaseModel):
    status: str
    message: Optional[str] = None
    last_updated: Optional[str] = None


class DashboardSnapshot(BaseModel):
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    workspace: str
    mode: Literal["paper", "live", "unknown"] = "unknown"
    configured: bool = False
    
    provider_summary: DashboardStatusSummary
    broker_sync_summary: DashboardStatusSummary
    portfolio_summary: dict[str, Any] = Field(default_factory=dict)
    open_orders_summary: dict[str, Any] = Field(default_factory=dict)
    risk_summary: DashboardStatusSummary
    kill_switch_summary: dict[str, Any] = Field(default_factory=dict)
    heartbeat_summary: DashboardStatusSummary
    audit_summary: dict[str, Any] = Field(default_factory=dict)
    safety_plan_summary: dict[str, Any] = Field(default_factory=dict)
    
    recent_events: List[dict[str, Any]] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
