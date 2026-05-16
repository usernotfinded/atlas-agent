"""Minimal safe quote source for market-order live-submit gating."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


DEFAULT_MAX_QUOTE_AGE_SECONDS = 15


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    bid: float
    ask: float
    timestamp: datetime
    source: str = "unknown"


class QuoteProvider(Protocol):
    def get_quote(self, symbol: str) -> MarketQuote | None:
        ...


def validate_market_quote(
    quote: MarketQuote | None,
    expected_symbol: str,
    max_age_seconds: float = DEFAULT_MAX_QUOTE_AGE_SECONDS,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Validate a MarketQuote for order submission.

    Returns (ok, reason_code).
    """
    if quote is None:
        return False, "market_quote_unavailable"

    if not isinstance(quote.symbol, str) or not quote.symbol:
        return False, "market_quote_invalid"

    if quote.symbol.upper() != expected_symbol.upper():
        return False, "market_quote_symbol_mismatch"

    for label, value in (("bid", quote.bid), ("ask", quote.ask)):
        if value is None:
            return False, "market_quote_invalid"
        if not isinstance(value, (int, float)):
            return False, "market_quote_invalid"
        if math.isnan(value) or math.isinf(value):
            return False, "market_quote_invalid"
        if value <= 0:
            return False, "market_quote_invalid"

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


def conservative_price_for_side(quote: MarketQuote, side: str) -> float:
    """Return conservative price for order side.

    - buy -> ask
    - sell -> bid
    """
    side_lower = side.lower()
    if side_lower == "buy":
        return quote.ask
    if side_lower == "sell":
        return quote.bid
    raise ValueError(f"Unsupported order side: {side}")
