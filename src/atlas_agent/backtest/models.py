from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional, Dict
from pydantic import BaseModel, Field


class BacktestConfig(BaseModel):
    run_id: str = Field(default_factory=lambda: f"bt-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    symbol: str
    data_path: str
    initial_equity: float = 10000.0
    slippage_bps: float = 0.0
    commission_bps: float = 0.0
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    strategy_mode: str = "buy_and_hold"
    strategy_parameters: Dict[str, Any] = Field(default_factory=dict)
    benchmark_mode: str = "buy_and_hold"
    benchmark_symbol: str = "SPY"
    benchmark_data_path: Optional[str] = None
    risk_enabled: bool = True
    kill_switch_state: bool = False


class MarketBar(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: Optional[str] = None


class BacktestOrder(BaseModel):
    order_id: str
    timestamp: datetime
    symbol: str
    side: Literal["buy", "sell"]
    type: Literal["market", "limit"] = "market"
    quantity: float
    price: Optional[float] = None  # Expected price or limit price
    status: Literal["proposed", "filled", "blocked", "cancelled"] = "proposed"


class BacktestFill(BaseModel):
    fill_id: str
    order_id: str
    timestamp: datetime
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float
    price: float
    notional: float
    commission: float = 0.0
    slippage: float = 0.0


class BacktestPosition(BaseModel):
    symbol: str
    quantity: float = 0.0
    average_entry_price: float = 0.0
    notional: float = 0.0


class BacktestMetrics(BaseModel):
    total_return_pct: float
    annualized_return_pct: Optional[float] = None
    max_drawdown_pct: float
    trade_count: int
    win_rate: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    best_trade_pct: Optional[float] = None
    worst_trade_pct: Optional[float] = None
    average_trade_pct: Optional[float] = None
    exposure_time_pct: Optional[float] = None
    buy_and_hold_return_pct: Optional[float] = None
    final_equity: float
    initial_equity: float


class BacktestResult(BaseModel):
    run_id: str
    status: Literal["completed", "failed", "blocked"]
    config: BacktestConfig
    metrics: BacktestMetrics
    strategy_metadata: Dict[str, Any] = Field(default_factory=dict)
    benchmark: Dict[str, Any] = Field(default_factory=dict)
    fills: List[BacktestFill] = Field(default_factory=list)
    equity_curve: List[Dict[str, Any]] = Field(default_factory=list)  # List of {timestamp, equity}
    diagnostics: Dict[str, Any] = Field(default_factory=dict)
    started_at: datetime
    completed_at: Optional[datetime] = None
