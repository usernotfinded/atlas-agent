# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    strategies/breakout.py
# PURPOSE: Donchian-channel breakout. Buys when price closes above the highest high
#          of the lookback window, sells when it closes below the lowest low.
# DEPS:    ai.decision_schema (the shared decision type), market_data.base (Bar)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from dataclasses import dataclass

from atlas_agent.ai.decision_schema import AIDecision, ProposedOrder
from atlas_agent.market_data.base import Bar


# ==============================================================================
# DONCHIAN BREAKOUT
# ==============================================================================

@dataclass(frozen=True)
class BreakoutStrategy:
    name: str = "breakout"
    lookback: int = 20

    def decide(self, bars: list[Bar]) -> AIDecision:
        """Propose a trade when price breaks out of its recent range.

        Args:
            bars: the price history. Needs `lookback + 1` bars: the window, plus the
                bar being tested against it.

        Returns:
            An AIDecision. A hold whenever there is not enough history, or the close
            sits inside the channel.

        Raises:
            ValueError: if `bars` is empty.
        """
        if not bars:
            raise ValueError("bars are required")

        sorted_bars = sorted(bars, key=lambda item: item.date)
        latest = sorted_bars[-1]

        # lookback + 1: the channel is built from the PRIOR bars, and the latest close is
        # tested against it. Including the latest bar in its own window would be circular
        # — its high would define the very level it is meant to break, so nothing could
        # ever break out.
        if len(sorted_bars) < self.lookback + 1:
            return _hold(latest.symbol, "not enough bars to build the breakout channel")

        window = sorted_bars[-(self.lookback + 1) : -1]
        channel_high = max(bar.high for bar in window)
        channel_low = min(bar.low for bar in window)

        # Strict > and <, not >= and <=. Touching the level is not breaking it: an equal
        # close is the range holding, and treating it as a breakout would fire a signal
        # on every flat stretch that grazes its own boundary.
        if latest.close > channel_high:
            return AIDecision(
                action="buy",
                symbol=latest.symbol,
                confidence=_confidence(latest.close - channel_high, channel_high),
                time_horizon="swing",
                reasoning_summary=(
                    f"close {latest.close:.2f} broke above the {self.lookback}-bar high {channel_high:.2f}"
                ),
                risk_notes="position size must be capped by risk manager",
                proposed_order=ProposedOrder(side="buy", quantity=1, limit_price=latest.close),
            )

        if latest.close < channel_low:
            return AIDecision(
                action="sell",
                symbol=latest.symbol,
                confidence=_confidence(channel_low - latest.close, channel_low),
                time_horizon="swing",
                reasoning_summary=(
                    f"close {latest.close:.2f} broke below the {self.lookback}-bar low {channel_low:.2f}"
                ),
                risk_notes="sell only existing long exposure",
                proposed_order=ProposedOrder(side="sell", quantity=1, limit_price=latest.close),
            )

        return _hold(
            latest.symbol,
            f"close {latest.close:.2f} is inside the channel [{channel_low:.2f}, {channel_high:.2f}]",
        )


# --- Helpers ---

def _confidence(breach: float, level: float) -> float:
    # Confidence is the breach expressed as a FRACTION of the level, not an absolute
    # move: breaking a $10 stock by $1 is a far stronger signal than breaking a $1000
    # one by the same dollar. Scaled by 20 so that a 5% breach reads as full conviction,
    # and clamped to [0, 1] because the risk gate requires that range.
    if level <= 0:
        return 0.0
    return min(max((breach / level) * 20.0, 0.0), 1.0)


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
