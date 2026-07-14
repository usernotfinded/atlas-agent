# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    market/session.py
# PURPOSE: Answers "is the market open right now?". Consumed by the deadman switch
#          (which stands down when it is not) and by the risk gate that enforces
#          market hours, so a wrong answer here has real consequences.
# DEPS:    zoneinfo (DST-correct exchange time), market.calendar (the hours)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from atlas_agent.market.calendar import MarketConfig


# ==============================================================================
# SESSION DETECTOR
# ==============================================================================

class MarketSessionDetector:
    def __init__(self, config: MarketConfig | None = None):
        self.config = config or MarketConfig.default()

    def get_state(self, now: datetime.datetime | None = None) -> str:
        """Classify `now` into a session state.

        Returns:
            One of: unknown, weekend, closed, premarket, open, afterhours.
        """
        if now is None:
            now = datetime.datetime.now(datetime.timezone.utc)

        try:
            tz = ZoneInfo(self.config.timezone)
        except ZoneInfoNotFoundError:
            # "unknown", not a guess. Callers treat unknown as "not open" — a system
            # with a broken tz database must not conclude the market is trading.
            return "unknown"

        # Converted to EXCHANGE-local time, never machine-local. zoneinfo also handles
        # DST, which is the whole reason this is not a naive UTC offset: the NYSE open
        # moves against UTC twice a year.
        local_time = now.astimezone(tz)

        # Check weekend
        if local_time.weekday() >= 5:  # 5=Saturday, 6=Sunday
            return "weekend"

        # String comparison works because "%H:%M" is zero-padded and fixed-width, so
        # lexicographic order and chronological order coincide.
        current_time_str = local_time.strftime("%H:%M")

        # Only "open" means the core session. premarket and afterhours are reported
        # distinctly rather than lumped in with it: they are tradeable at some venues
        # but far thinner, and a caller that wants to refuse them must be able to.
        if current_time_str < "04:00":
            return "closed"
        elif "04:00" <= current_time_str < self.config.core_open:
            return "premarket"
        elif self.config.core_open <= current_time_str < self.config.core_close:
            return "open"
        elif self.config.core_close <= current_time_str < "20:00":
            return "afterhours"
        else:
            return "closed"
