# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    strategies/rsi.py
# PURPOSE: RSI mean-reversion strategy. Buys when the relative strength index falls
#          below the oversold threshold, sells when it rises above the overbought one.
# DEPS:    ai.decision_schema (the shared decision type), market_data.base (Bar)
#
# NOTE:    The RSI maths is shared with backtest/strategies.py (_rsi), so a signal
#          seen here and a signal seen in a backtest are computed identically. Two
#          implementations would eventually disagree, and the disagreement would only
#          show up as a live trade that the backtest said would never happen.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from dataclasses import dataclass

from atlas_agent.ai.decision_schema import AIDecision, ProposedOrder
from atlas_agent.backtest.strategies import _rsi
from atlas_agent.market_data.base import Bar


# ==============================================================================
# RSI MEAN REVERSION
# ==============================================================================

@dataclass(frozen=True)
class RSIStrategy:
    name: str = "rsi"
    period: int = 14
    oversold: float = 30.0
    overbought: float = 70.0

    def decide(self, bars: list[Bar]) -> AIDecision:
        """Propose a trade from the RSI of the closing prices.

        Args:
            bars: the price history. Only the last `period + 1` closes are used.

        Returns:
            An AIDecision. A hold whenever there is not enough history, or the RSI
            sits between the two thresholds.

        Raises:
            ValueError: if `bars` is empty.
        """
        if not bars:
            raise ValueError("bars are required")

        # Re-sorted defensively. The engine already delivers bars in order, but reading
        # a "latest" bar from the middle of history would silently invert the signal.
        sorted_bars = sorted(bars, key=lambda item: item.date)
        latest = sorted_bars[-1]

        # RSI over N periods needs N close-to-close CHANGES, hence N+1 closes. Computing
        # it on fewer would divide by `period` while summing over a shorter window,
        # understating both averages and pulling the index toward the middle — a
        # plausible-looking number that means nothing.
        if len(sorted_bars) < self.period + 1:
            return _hold(latest.symbol, "not enough bars to compute RSI")

        closes = [bar.close for bar in sorted_bars]
        rsi = _rsi(closes, self.period)

        # Mean reversion: oversold is a BUY (the fall is assumed to overshoot), and
        # overbought is a SELL. This is the opposite of a momentum reading of the same
        # number, which is why the thresholds are named rather than hardcoded.
        if rsi <= self.oversold:
            return AIDecision(
                action="buy",
                symbol=latest.symbol,
                # Confidence scales with how far past the threshold we are, so an RSI of
                # 10 is a stronger signal than one of 29. Normalised by the distance from
                # the threshold to the extreme, and clamped, so it stays within [0, 1] —
                # which the risk gate requires.
                confidence=_confidence(self.oversold - rsi, self.oversold),
                time_horizon="swing",
                reasoning_summary=f"RSI {rsi:.1f} is at or below the oversold threshold {self.oversold:.1f}",
                risk_notes="position size must be capped by risk manager",
                proposed_order=ProposedOrder(side="buy", quantity=1, limit_price=latest.close),
            )

        if rsi >= self.overbought:
            return AIDecision(
                action="sell",
                symbol=latest.symbol,
                confidence=_confidence(rsi - self.overbought, 100.0 - self.overbought),
                time_horizon="swing",
                reasoning_summary=f"RSI {rsi:.1f} is at or above the overbought threshold {self.overbought:.1f}",
                risk_notes="sell only existing long exposure",
                proposed_order=ProposedOrder(side="sell", quantity=1, limit_price=latest.close),
            )

        return _hold(latest.symbol, f"RSI {rsi:.1f} is between the thresholds")


# --- Helpers ---

def _confidence(distance: float, span: float) -> float:
    # `span` is the distance from the threshold to the extreme (0 or 100). A zero span
    # would mean the threshold IS the extreme, leaving no room to be more confident —
    # so it collapses to full confidence rather than dividing by zero.
    if span <= 0:
        return 1.0
    return min(max(distance / span, 0.0), 1.0)


def _hold(symbol: str, reason: str) -> AIDecision:
    # A hold is recorded with its reason, so a replay can answer "why did it do nothing?"
    # — the question people actually ask after a move they missed.
    return AIDecision(
        action="hold",
        symbol=symbol,
        confidence=0.0,
        time_horizon="intraday",
        reasoning_summary=reason,
        risk_notes="no order proposed",
        proposed_order=None,
    )
