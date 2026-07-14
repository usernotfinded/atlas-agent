# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    market/calendar.py
# PURPOSE: Exchange trading hours. Defaults to US equities (NYSE/NASDAQ core hours).
# DEPS:    stdlib only
#
# NOTE:    Regular hours only — this knows nothing about market holidays. A holiday
#          therefore reads as a normal weekday. In practice the broker rejects the
#          order anyway, but do not treat "open" here as a guarantee of a live venue.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


# ==============================================================================
# MARKET HOURS
# ==============================================================================

class MarketConfig:
    def __init__(
        self,
        timezone: str = "America/New_York",
        core_open: str = "09:30",
        core_close: str = "16:00",
    ):
        self.timezone = timezone
        self.core_open = core_open
        self.core_close = core_close

    @classmethod
    def default(cls) -> MarketConfig:
        return cls()
