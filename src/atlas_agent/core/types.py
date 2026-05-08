from typing import Literal, Optional, Any, List
from pydantic import BaseModel

class CostModel(BaseModel):
    slippage_bps: float
    commission: float

class TradeThesis(BaseModel):
    direction_rationale: str
    timeframe: Literal["intraday", "swing", "position"]
    catalyst: str
    invalidation_condition: str
    risk_reward_estimate: float
    confidence: Literal["low", "medium", "high"]
    bear_case_acknowledged: str

class OrderProposal(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float
    order_type: Literal["market", "limit"]
    limit_price: Optional[float] = None
    thesis: TradeThesis
    invalidation_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    time_in_force: str = "day"

class OrderResult(BaseModel):
    order_id: str
    status: str
    filled: bool
    average_price: Optional[float] = None

class OrderProposalResult(BaseModel):
    status: str
    order: Optional[OrderResult] = None
    approval_pending: bool

class QuoteData(BaseModel):
    price: float
    change_pct: float
    volume: float

class Bar(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float

class OrderbookSnapshot(BaseModel):
    bids: List[tuple[float, float]]
    asks: List[tuple[float, float]]

class IndicatorSpec(BaseModel):
    name: str
    parameters: dict

class IndicatorResult(BaseModel):
    values: List[float]

class BacktestReport(BaseModel):
    sharpe: float
    max_drawdown: float
    total_return: float
    trades: int

class MonteCarloResult(BaseModel):
    p5_drawdown: float
    p95_return: float

class CorrelationMatrix(BaseModel):
    symbols: List[str]
    matrix: List[List[float]]

class FilterSpec(BaseModel):
    field: str
    operator: str
    value: float

class ScreenerResult(BaseModel):
    symbol: str
    metrics: dict

class Position(BaseModel):
    symbol: str
    quantity: float
    average_price: float
    current_price: float
    pnl_pct: float

class AccountSnapshot(BaseModel):
    equity: float
    cash: float
    buying_power: float
    margin_used: float

class FlattenResult(BaseModel):
    orders: List[OrderResult]

class JournalEntry(BaseModel):
    timestamp: str
    entry_type: str
    content: str
    symbol: Optional[str] = None

class LessonEntry(BaseModel):
    date: str
    category: str
    content: str

class TradeSummary(BaseModel):
    total_trades: int
    win_rate: float
    pnl: float

class SkillContent(BaseModel):
    name: str
    pattern: str
    evidence: str

class SkillSummary(BaseModel):
    name: str
    status: str

class SearchResult(BaseModel):
    file: str
    snippet: str
    score: float

class SearchResultItem(BaseModel):
    title: str
    url: str
    snippet: str

class ResearchReport(BaseModel):
    query: str
    summary: str
    sources: List[str]

class ShellResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str

class TimeInfo(BaseModel):
    utc_time: str
    local_time: str
    market_hours: bool

class MarketStatus(BaseModel):
    is_open: bool
    next_open: str
    next_close: str

class LimitsSnapshot(BaseModel):
    max_daily_loss_pct: float
    approval_max_position_pct: float
    circuit_breaker_mode: str

class TrustModeInfo(BaseModel):
    mode: str
    thresholds: dict

class Session(BaseModel):
    id: str
    turn_count: int
    has_summarized: bool
    
    def is_done(self) -> bool:
        return False
        
    def mark_done(self, reason: str) -> None:
        pass

class UserApprovalPending(BaseModel):
    approval_id: str
    notification: str
    timeout_seconds: int

class SessionTrigger(BaseModel):
    source: str
    event_data: Optional[dict] = None

class NewsItem(BaseModel):
    title: str
    source: str
    summary: str
    url: str
    timestamp: str

class EconomicEvent(BaseModel):
    event: str
    date: str
    impact: str
    actual: Optional[str] = None
    forecast: Optional[str] = None

class EarningsItem(BaseModel):
    symbol: str
    date: str
    estimate: Optional[float] = None
    actual: Optional[float] = None

class UserResponse(BaseModel):
    decision: Literal["approve", "reject", "modify", "timeout"]
    feedback: Optional[str] = None
    modified_order: Optional[OrderProposal] = None

class ApprovalRequirement(BaseModel):
    requires_approval: bool
    reason: str
    escalation_note: Optional[str] = None
