# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    execution/quotes.py
# PURPOSE: Supplies the reference price a market order needs before risk can size
#          it — and, more importantly, refuses to supply one it does not trust.
#          A stale or malformed quote here would let a market order be risk-checked
#          against a price that no longer exists.
# DEPS:    stdlib only (math, datetime) — the provider is injected via Protocol
# ==============================================================================

"""Minimal safe quote source for market-order live-submit gating."""

# --- IMPORTS ---
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


# --- CONFIGURATIONS & CONSTANTS ---

# 15 seconds. Short because this gates LIVE market orders: a price older than this
# is a guess, and sizing a real order against a guess is how a notional cap gets
# quietly breached in a fast market.
DEFAULT_MAX_QUOTE_AGE_SECONDS = 15


# ==============================================================================
# QUOTE MODEL
# ==============================================================================

@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    bid: float
    ask: float
    timestamp: datetime
    source: str = "unknown"


# Structural typing: any object with get_quote() qualifies. Keeps this module free
# of a dependency on any particular market-data vendor.
class QuoteProvider(Protocol):
    def get_quote(self, symbol: str) -> MarketQuote | None:
        ...


# ==============================================================================
# VALIDATION
# ==============================================================================

def validate_market_quote(
    quote: MarketQuote | None,
    expected_symbol: str,
    max_age_seconds: float = DEFAULT_MAX_QUOTE_AGE_SECONDS,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Validate a MarketQuote for order submission.

    Returns (ok, reason_code).
    """
    # Every branch below returns FALSE. There is no "close enough" quote: an order
    # that cannot be priced from trusted data must not be sent, and the reason codes
    # exist so the rejection is explainable in the audit trail rather than mysterious.
    if quote is None:
        return False, "market_quote_unavailable"

    if not isinstance(quote.symbol, str) or not quote.symbol:
        return False, "market_quote_invalid"

    # The symbol is re-checked against what the CALLER asked for. A provider returning
    # a quote for the wrong ticker — a cache mixup, a bad mapping — would otherwise
    # price an order for AAPL off the book for MSFT.
    if quote.symbol.upper() != expected_symbol.upper():
        return False, "market_quote_symbol_mismatch"

    # NaN and inf are rejected explicitly, not caught by the `<= 0` test below: NaN
    # fails every comparison silently, so `NaN <= 0` is False and it would sail
    # through as a "valid" price.
    for label, value in (("bid", quote.bid), ("ask", quote.ask)):
        if value is None:
            return False, "market_quote_invalid"
        if not isinstance(value, (int, float)):
            return False, "market_quote_invalid"
        if math.isnan(value) or math.isinf(value):
            return False, "market_quote_invalid"
        if value <= 0:
            return False, "market_quote_invalid"

    # A crossed book (ask < bid) is not a real market. It means the feed is broken or
    # the two sides came from different snapshots, and pricing against it would produce
    # a nonsense fill assumption.
    if quote.ask < quote.bid:
        return False, "market_quote_invalid"

    ts = quote.timestamp
    if ts is None:
        return False, "market_quote_invalid"
    if not isinstance(ts, datetime):
        return False, "market_quote_invalid"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)

    if now is None:
        now = datetime.now(UTC)
    age = (now - ts).total_seconds()
    if age > max_age_seconds:
        return False, "market_quote_stale"

    return True, ""


# ==============================================================================
# CONSERVATIVE PRICING
# ==============================================================================

def conservative_price_for_side(quote: MarketQuote, side: str) -> float:
    """Return conservative price for order side.

    - buy -> ask
    - sell -> bid
    """
    # Always the side of the book that is WORSE for us: a buy is priced at the ask
    # (the most we would pay), a sell at the bid (the least we would get). This makes
    # the notional an over-estimate, so risk limits bind slightly early rather than
    # slightly late. Using the mid would systematically under-state exposure and let
    # orders through that the caps were meant to stop.
    side_lower = side.lower()
    if side_lower == "buy":
        return quote.ask
    if side_lower == "sell":
        return quote.bid
    # Raise rather than pick a default: an unrecognised side is a bug in the caller,
    # and guessing a price for it would be worse than failing.
    raise ValueError(f"Unsupported order side: {side}")
