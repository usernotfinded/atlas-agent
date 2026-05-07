import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch

from atlas_agent.market.calendar import MarketConfig
from atlas_agent.market.session import MarketSessionDetector

def test_market_session_open():
    detector = MarketSessionDetector()
    tz = ZoneInfo("America/New_York")
    # A random Tuesday at 10:00 AM
    dt = datetime.datetime(2023, 10, 3, 10, 0, tzinfo=tz)
    assert detector.get_state(dt) == "open"

def test_market_session_premarket():
    detector = MarketSessionDetector()
    tz = ZoneInfo("America/New_York")
    # A random Tuesday at 8:00 AM
    dt = datetime.datetime(2023, 10, 3, 8, 0, tzinfo=tz)
    assert detector.get_state(dt) == "premarket"

def test_market_session_afterhours():
    detector = MarketSessionDetector()
    tz = ZoneInfo("America/New_York")
    # A random Tuesday at 17:00 PM
    dt = datetime.datetime(2023, 10, 3, 17, 0, tzinfo=tz)
    assert detector.get_state(dt) == "afterhours"

def test_market_session_weekend():
    detector = MarketSessionDetector()
    tz = ZoneInfo("America/New_York")
    # A Saturday at 10:00 AM
    dt = datetime.datetime(2023, 10, 7, 10, 0, tzinfo=tz)
    assert detector.get_state(dt) == "weekend"

def test_market_session_closed_night():
    detector = MarketSessionDetector()
    tz = ZoneInfo("America/New_York")
    # A Tuesday at 2:00 AM
    dt = datetime.datetime(2023, 10, 3, 2, 0, tzinfo=tz)
    assert detector.get_state(dt) == "closed"

def test_market_session_unknown_timezone():
    config = MarketConfig(timezone="Fake/Timezone")
    detector = MarketSessionDetector(config)
    assert detector.get_state() == "unknown"
