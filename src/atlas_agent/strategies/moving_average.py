from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean

from atlas_agent.ai.decision_schema import AIDecision, ProposedOrder
from atlas_agent.market_data.base import Bar


@dataclass(frozen=True)
class MovingAverageStrategy:
    name: str = "moving_average"
    short_window: int = 3
    long_window: int = 5
    threshold: float = 0.002

    def decide(self, bars: list[Bar]) -> AIDecision:
        if not bars:
            raise ValueError("bars are required")
        sorted_bars = sorted(bars, key=lambda item: item.date)
        latest = sorted_bars[-1]
        if len(sorted_bars) < self.long_window:
            return _hold(latest.symbol, "not enough bars")
        closes = [bar.close for bar in sorted_bars]
        short_ma = fmean(closes[-self.short_window :])
        long_ma = fmean(closes[-self.long_window :])
        gap = (short_ma - long_ma) / long_ma
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


def _hold(symbol: str, reason: str) -> AIDecision:
    return AIDecision(
        action="hold",
        symbol=symbol,
        confidence=0.0,
        time_horizon="intraday",
        reasoning_summary=reason,
        risk_notes="no order proposed",
        proposed_order=None,
    )

