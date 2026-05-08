from typing import Literal, Optional, Any
from pydantic import BaseModel

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
