# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    agent/autonomous_paper_models.py
# PURPOSE: The state and metrics of an autonomous paper run.
# DEPS:    pydantic, backtest.models — the paper loop reuses the BACKTEST fill and
#          position types on purpose, so a paper run and a backtest are measured by
#          exactly the same arithmetic.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from atlas_agent.backtest.models import BacktestFill, BacktestOrder, BacktestPosition


class StatefulPaperConfig(BaseModel):
    run_id: str
    symbol: str
    strategy_id: str
    strategy_parameters: dict[str, Any] = Field(default_factory=dict)
    data_path: str
    output_dir: str
    state_dir: str
    initial_cash: float = Field(gt=0, default=10_000.0)
    commission_bps: float = Field(ge=0, default=1.0)
    slippage_bps: float = Field(ge=0, default=1.0)
    max_orders_per_cycle: int = Field(gt=0, default=10)
    fill_timing: Literal["same_bar", "next_bar"] = "next_bar"

    @field_validator("commission_bps", "slippage_bps", mode="before")
    @classmethod
    def _default_bps_when_none(cls, value: Any) -> Any:
        """Allow callers to pass None and fall back to conservative defaults."""
        return 1.0 if value is None else value


class StatefulPaperCursor(BaseModel):
    last_processed_bar_index: int = -1
    last_processed_bar_timestamp: str | None = None
    processed_bar_hashes: list[str] = Field(default_factory=list)


class StatefulPaperState(BaseModel):
    run_id: str
    symbol: str
    strategy_id: str
    data_path: str
    cash: float
    positions: dict[str, BacktestPosition]
    cursor: StatefulPaperCursor
    fill_history: list[BacktestFill]
    pending_orders: list[BacktestOrder] = Field(default_factory=list)
    decision_refs: list[dict[str, Any]]
    metrics_history: list[dict[str, Any]]
    created_at: str
    updated_at: str
    status: Literal["active", "completed", "failed"] = "active"
    errors: list[str] = Field(default_factory=list)


class StatefulPaperMetrics(BaseModel):
    starting_cash: float
    ending_cash: float
    ending_equity: float
    realized_pnl: float | None = None
    unrealized_pnl: float | None = None
    total_return_pct: float
    max_drawdown_pct: float
    number_of_trades: int
    number_of_fills: int
    number_of_rejections: int
    turnover: float | None = None
    gross_exposure: float
    net_exposure: float
    total_commission: float
    total_slippage: float
    bars_processed: int
    data_source_redacted: str
    generated_at: str
    notes: list[str] = Field(default_factory=list)


class StatefulPaperResult(BaseModel):
    run_id: str
    status: Literal["completed", "failed", "blocked", "no_new_data"]
    bars_processed_this_run: int
    total_bars_processed: int
    decisions_path: str
    fills_path: str
    metrics_path: str
    checkpoint_path: str
    manifest_path: str
    audit_log_path: str
    metrics: StatefulPaperMetrics | None = None
    errors: list[str] = Field(default_factory=list)
