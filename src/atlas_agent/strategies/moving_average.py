# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    strategies/moving_average.py
# PURPOSE: A textbook moving-average crossover. Deliberately simple: it exists to
#          exercise the pipeline end-to-end with no LLM in the loop, not to be a
#          strategy anyone should trade.
# DEPS:    ai.decision_schema (the shared decision type), market_data.base (Bar)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean

from atlas_agent.ai.decision_schema import AIDecision, ProposedOrder
from atlas_agent.market_data.base import Bar


# ==============================================================================
# MOVING AVERAGE CROSSOVER
# ==============================================================================

@dataclass(frozen=True)
class MovingAverageStrategy:
    name: str = "moving_average"
    short_window: int = 3
    long_window: int = 5
    # A dead band around zero. Without it the strategy would flip on every marginal
    # crossing and churn the account in commissions.
    threshold: float = 0.002

    def decide(self, bars: list[Bar]) -> AIDecision:
        if not bars:
            raise ValueError("bars are required")
        # Re-sorted even though the CSV provider already sorts. Cheap, and the cost of
        # being wrong is silently reading a "latest" bar from the middle of history.
        sorted_bars = sorted(bars, key=lambda item: item.date)
        latest = sorted_bars[-1]
        # Too little history → HOLD, never a trade. A moving average computed over fewer
        # bars than its own window is not a moving average, and acting on it would be
        # acting on noise.
        if len(sorted_bars) < self.long_window:
            return _hold(latest.symbol, "not enough bars")
        closes = [bar.close for bar in sorted_bars]
        short_ma = fmean(closes[-self.short_window :])
        long_ma = fmean(closes[-self.long_window :])
        gap = (short_ma - long_ma) / long_ma
        # Confidence scales with how far past the threshold we are, capped at 1.0. The
        # max(..., 0.0001) guards a zero threshold from producing a division by zero.
        confidence = min(abs(gap) / max(self.threshold * 4, 0.0001), 1.0)
        if gap > self.threshold:
            return AIDecision(
                action="buy",
                symbol=latest.symbol,
                confidence=confidence,
                time_horizon="swing",
                reasoning_summary="short moving average is above long moving average",
                risk_notes="position size must be capped by risk manager",
                proposed_order=ProposedOrder(side="buy", quantity=1, limit_price=latest.close),
            )
        if gap < -self.threshold:
            return AIDecision(
                action="sell",
                symbol=latest.symbol,
                confidence=confidence,
                time_horizon="swing",
                reasoning_summary="short moving average is below long moving average",
                risk_notes="sell only existing long exposure",
                proposed_order=ProposedOrder(side="sell", quantity=1, limit_price=latest.close),
            )
        return _hold(latest.symbol, "moving averages are within threshold")


# --- Helpers ---

def _hold(symbol: str, reason: str) -> AIDecision:
    # A hold is a real decision, not an absence of one — it is recorded with its reason
    # so a replay can show WHY the agent did nothing, which is the question people
    # actually ask after a move they missed.
    return AIDecision(
        action="hold",
        symbol=symbol,
        confidence=0.0,
        time_horizon="intraday",
        reasoning_summary=reason,
        risk_notes="no order proposed",
        proposed_order=None,
    )

