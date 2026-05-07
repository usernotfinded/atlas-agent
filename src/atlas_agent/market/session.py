from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from atlas_agent.market.calendar import MarketConfig


class MarketSessionDetector:
    def __init__(self, config: MarketConfig | None = None):
        self.config = config or MarketConfig.default()

    def get_state(self, now: datetime.datetime | None = None) -> str:
        if now is None:
            now = datetime.datetime.now(datetime.timezone.utc)
        
        try:
            tz = ZoneInfo(self.config.timezone)
        except ZoneInfoNotFoundError:
            return "unknown"

        local_time = now.astimezone(tz)
        
        # Check weekend
        if local_time.weekday() >= 5:  # 5=Saturday, 6=Sunday
            return "weekend"
            
        current_time_str = local_time.strftime("%H:%M")
        
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
