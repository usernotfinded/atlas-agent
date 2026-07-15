# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/gateway/telegram/test_ratelimit.py
# PURPOSE: Verifies ratelimit behavior and regression expectations.
# DEPS:    dataclasses, datetime, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from atlas_agent.gateway.telegram.ratelimit import RateLimitConfig, TelegramRateLimiter


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

@dataclass
class FakeClock:
    current: datetime

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: int) -> None:
        self.current = self.current + timedelta(seconds=seconds)


def test_general_rate_limit_blocks_after_capacity() -> None:
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    limiter = TelegramRateLimiter(
        config=RateLimitConfig(commands_per_minute=3, money_commands_per_minute=2),
        now_func=clock.now,
    )

    assert limiter.check("42").allowed
    assert limiter.check("42").allowed
    assert limiter.check("42").allowed
    denied = limiter.check("42")
    assert not denied.allowed
    assert denied.bucket == "general"
    assert denied.retry_after_seconds >= 1


def test_money_rate_limit_independent_of_general() -> None:
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    limiter = TelegramRateLimiter(
        config=RateLimitConfig(commands_per_minute=10, money_commands_per_minute=2),
        now_func=clock.now,
    )

    assert limiter.check("100", money_touching=True).allowed
    assert limiter.check("100", money_touching=True).allowed
    denied = limiter.check("100", money_touching=True)
    assert not denied.allowed
    assert denied.bucket == "money"

    # non-money command still allowed because general bucket has capacity
    assert limiter.check("100", money_touching=False).allowed


def test_bucket_refills_over_time() -> None:
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    limiter = TelegramRateLimiter(
        config=RateLimitConfig(commands_per_minute=2, money_commands_per_minute=1),
        now_func=clock.now,
    )

    assert limiter.check("x").allowed
    assert limiter.check("x").allowed
    denied = limiter.check("x")
    assert not denied.allowed

    clock.advance(31)  # refill ~1 token for cap=2/min
    assert limiter.check("x").allowed


def test_money_denial_refunds_general_token() -> None:
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    limiter = TelegramRateLimiter(
        config=RateLimitConfig(commands_per_minute=3, money_commands_per_minute=1),
        now_func=clock.now,
    )

    assert limiter.check("a", money_touching=True).allowed
    denied = limiter.check("a", money_touching=True)
    assert not denied.allowed
    assert denied.bucket == "money"

    # still 2 non-money operations available if refund worked
    assert limiter.check("a").allowed
    assert limiter.check("a").allowed
    denied_general = limiter.check("a")
    assert not denied_general.allowed
    assert denied_general.bucket == "general"


def test_limits_are_per_chat_id() -> None:
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    limiter = TelegramRateLimiter(
        config=RateLimitConfig(commands_per_minute=1, money_commands_per_minute=1),
        now_func=clock.now,
    )

    assert limiter.check("u1").allowed
    assert not limiter.check("u1").allowed
    assert limiter.check("u2").allowed
