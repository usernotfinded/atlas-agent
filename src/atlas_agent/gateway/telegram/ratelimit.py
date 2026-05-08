from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import threading
from typing import Callable


@dataclass(frozen=True)
class RateLimitConfig:
    commands_per_minute: int = 30
    money_commands_per_minute: int = 5

    def __post_init__(self) -> None:
        if self.commands_per_minute <= 0:
            raise ValueError("commands_per_minute must be positive")
        if self.money_commands_per_minute <= 0:
            raise ValueError("money_commands_per_minute must be positive")


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int
    bucket: str
    remaining: float
    message: str


@dataclass
class _TokenBucket:
    capacity: float
    refill_per_second: float
    tokens: float
    updated_at: float

    def refill(self, now_ts: float) -> None:
        elapsed = max(now_ts - self.updated_at, 0.0)
        if elapsed <= 0:
            return
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_second)
        self.updated_at = now_ts

    def consume(self, amount: float, now_ts: float) -> tuple[bool, int]:
        self.refill(now_ts)
        if self.tokens >= amount:
            self.tokens -= amount
            return True, 0
        missing = amount - self.tokens
        wait_seconds = int(missing / self.refill_per_second) + 1
        return False, max(wait_seconds, 1)


class TelegramRateLimiter:
    def __init__(
        self,
        *,
        config: RateLimitConfig | None = None,
        now_func: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config or RateLimitConfig()
        self._now = now_func or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()
        self._general: dict[str, _TokenBucket] = {}
        self._money: dict[str, _TokenBucket] = {}

    def check(self, chat_id: str | int, *, money_touching: bool = False) -> RateLimitDecision:
        key = str(chat_id).strip()
        now_ts = self._now().timestamp()
        with self._lock:
            general_bucket = self._general.setdefault(
                key,
                _new_bucket(self.config.commands_per_minute, now_ts),
            )
            allowed_general, wait_general = general_bucket.consume(1.0, now_ts)
            if not allowed_general:
                return RateLimitDecision(
                    allowed=False,
                    retry_after_seconds=wait_general,
                    bucket="general",
                    remaining=max(general_bucket.tokens, 0.0),
                    message="rate limit exceeded: max 30 commands/minute",
                )
            if not money_touching:
                return RateLimitDecision(
                    allowed=True,
                    retry_after_seconds=0,
                    bucket="general",
                    remaining=max(general_bucket.tokens, 0.0),
                    message="ok",
                )

            money_bucket = self._money.setdefault(
                key,
                _new_bucket(self.config.money_commands_per_minute, now_ts),
            )
            allowed_money, wait_money = money_bucket.consume(1.0, now_ts)
            if not allowed_money:
                # refund general token when money bucket denies
                general_bucket.tokens = min(general_bucket.capacity, general_bucket.tokens + 1.0)
                return RateLimitDecision(
                    allowed=False,
                    retry_after_seconds=wait_money,
                    bucket="money",
                    remaining=max(money_bucket.tokens, 0.0),
                    message="rate limit exceeded: max 5 money-touching commands/minute",
                )
            return RateLimitDecision(
                allowed=True,
                retry_after_seconds=0,
                bucket="money",
                remaining=max(money_bucket.tokens, 0.0),
                message="ok",
            )

    def reset_chat(self, chat_id: str | int) -> None:
        key = str(chat_id).strip()
        with self._lock:
            self._general.pop(key, None)
            self._money.pop(key, None)

    def snapshot(self, chat_id: str | int) -> dict[str, float]:
        key = str(chat_id).strip()
        now_ts = self._now().timestamp()
        with self._lock:
            general = self._general.get(key)
            money = self._money.get(key)
            if general is not None:
                general.refill(now_ts)
            if money is not None:
                money.refill(now_ts)
            return {
                "general_tokens": general.tokens if general is not None else float(self.config.commands_per_minute),
                "money_tokens": money.tokens if money is not None else float(self.config.money_commands_per_minute),
            }


def _new_bucket(capacity: int, now_ts: float) -> _TokenBucket:
    return _TokenBucket(
        capacity=float(capacity),
        refill_per_second=float(capacity) / 60.0,
        tokens=float(capacity),
        updated_at=now_ts,
    )

