from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
