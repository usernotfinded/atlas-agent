from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from atlas_agent.gateway.services import ServiceResult
from atlas_agent.gateway.telegram.auth import TelegramAuth, TelegramAuthConfig
from atlas_agent.gateway.telegram.bot import TIMEOUT_MESSAGE, TelegramBotConfig, TelegramCommandBot
from atlas_agent.gateway.telegram.ratelimit import RateLimitConfig, TelegramRateLimiter


@dataclass
class FakeKeyring:
    store: dict[tuple[str, str], str] = field(default_factory=dict)

    def get_password(self, service_name: str, username: str) -> str | None:
        return self.store.get((service_name, username))

    def set_password(self, service_name: str, username: str, password: str) -> None:
        self.store[(service_name, username)] = password


class FakeTotp:
    def random_base32(self) -> str:
        return "TESTSECRET"

    def verify(self, secret: str, code: str, *, valid_window: int = 1) -> bool:
        return secret == "TESTSECRET" and code == "123456"


@dataclass
class FakeAudit:
    entries: list[dict[str, str]] = field(default_factory=list)

    async def log_command(
        self,
        *,
        chat_id: str,
        command: str,
        outcome: str,
        detail: str = "",
        ts_utc: str | None = None,
    ) -> None:
        self.entries.append(
            {
                "chat_id": chat_id,
                "command": command,
                "outcome": outcome,
                "detail": detail,
            }
        )


@dataclass
class FakeAgentService:
    async def status(self, actor: str) -> ServiceResult:
        return ServiceResult(
            ok=True,
            message="status ok",
            data={"symbol": "TEST-SYMBOL", "position_pct": 15.0, "position_size_usd": 12345},
        )

    async def plan(self, actor: str) -> ServiceResult:
        return ServiceResult(ok=True, message="plan ok")

    async def run(self, actor: str, mode: str = "auto") -> ServiceResult:
        if mode == "live":
            await asyncio.sleep(0.01)
        return ServiceResult(ok=True, message=f"run {mode}")

    async def learn(self, actor: str) -> ServiceResult:
        return ServiceResult(ok=True, message="learn ok")

    async def reflect(self, actor: str) -> ServiceResult:
        return ServiceResult(ok=True, message="reflect ok")

    async def positions(self, actor: str) -> ServiceResult:
        return ServiceResult(ok=True, message="positions", data={"ticker": "ETH-USD", "weight_pct": 22.4})

    async def memory_search(self, actor: str, query: str) -> ServiceResult:
        return ServiceResult(ok=True, message="memory", data={"query": query})

    async def skills(self, actor: str) -> ServiceResult:
        return ServiceResult(ok=True, message="skills", data={"active": 3})


@dataclass
class FakeOrderService:
    approved: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)

    async def pending(self, actor: str) -> ServiceResult:
        return ServiceResult(ok=True, message="pending", data={"count": 1})

    async def approve(self, actor: str, order_id: str) -> ServiceResult:
        self.approved.append(order_id)
        return ServiceResult(ok=True, message=f"approved {order_id}")

    async def reject(self, actor: str, order_id: str) -> ServiceResult:
        self.rejected.append(order_id)
        return ServiceResult(ok=True, message=f"rejected {order_id}")


@dataclass
class FakeKillSwitchService:
    kills: list[str] = field(default_factory=list)
    resumes: int = 0
    heartbeats: int = 0

    async def kill(self, actor: str, mode: str = "soft", reason: str = "") -> ServiceResult:
        self.kills.append(mode)
        return ServiceResult(ok=True, message=f"kill {mode}")

    async def resume(self, actor: str) -> ServiceResult:
        self.resumes += 1
        return ServiceResult(ok=True, message="resumed")

    async def heartbeat(self, actor: str, source: str = "telegram") -> ServiceResult:
        self.heartbeats += 1
        return ServiceResult(ok=True, message="heartbeat")

    async def status(self, actor: str) -> ServiceResult:
        return ServiceResult(ok=True, message="kill status")


def build_bot(*, allowed: tuple[str, ...] = ("100",), timeout_seconds: float = 0.2):
    auth = TelegramAuth(
        config=TelegramAuthConfig(
            allowed_users=frozenset(allowed),
            keyring_service="atlas-test-telegram",
            challenge_ttl_seconds=120,
            challenge_max_attempts=3,
        ),
        keyring_backend=FakeKeyring(),
        totp_backend=FakeTotp(),
    )
    rate = TelegramRateLimiter(
        config=RateLimitConfig(commands_per_minute=30, money_commands_per_minute=5),
        now_func=lambda: datetime.now(UTC),
    )
    audit = FakeAudit()
    order = FakeOrderService()
    kill = FakeKillSwitchService()
    bot = TelegramCommandBot(
        auth=auth,
        rate_limiter=rate,
        agent_service=FakeAgentService(),
        order_service=order,
        kill_switch_service=kill,
        audit_service=audit,
        config=TelegramBotConfig(command_timeout_seconds=timeout_seconds),
    )
    return bot, audit, order, kill


def test_unauthorized_chat_is_rejected() -> None:
    bot, audit, _, _ = build_bot()
    result = asyncio.run(bot.handle_text(chat_id="999", text="/status", actor="user:999"))
    assert result == "Accesso non autorizzato."
    assert audit.entries[-1]["outcome"] == "rejected"


def test_status_command_is_sanitized() -> None:
    bot, _, _, _ = build_bot()
    result = asyncio.run(bot.handle_text(chat_id="100", text="/status", actor="user:100"))
    assert "status ok" in result
    assert "position_size_usd: [REDACTED_USD]" in result
    assert "position_pct: 15.0" in result


def test_money_touching_command_requires_2fa_then_executes() -> None:
    bot, _, _, kill = build_bot()
    first = asyncio.run(bot.handle_text(chat_id="100", text="/kill flatten", actor="user:100"))
    assert first == "Conferma con codice TOTP"
    second = asyncio.run(bot.handle_text(chat_id="100", text="123456", actor="user:100"))
    assert "kill flatten" in second
    assert kill.kills == ["flatten"]


def test_run_live_requires_2fa() -> None:
    bot, _, _, _ = build_bot()
    first = asyncio.run(bot.handle_text(chat_id="100", text="/run live", actor="user:100"))
    assert first == "Conferma con codice TOTP"
    second = asyncio.run(bot.handle_text(chat_id="100", text="123456", actor="user:100"))
    assert "run live" in second


def test_rate_limit_blocks_excess_commands() -> None:
    bot, _, _, _ = build_bot()
    bot.rate_limiter = TelegramRateLimiter(
        config=RateLimitConfig(commands_per_minute=1, money_commands_per_minute=1),
        now_func=lambda: datetime.now(UTC),
    )
    first = asyncio.run(bot.handle_text(chat_id="100", text="/status", actor="user:100"))
    second = asyncio.run(bot.handle_text(chat_id="100", text="/plan", actor="user:100"))
    assert "status ok" in first
    assert second == "Troppi comandi, riprova più tardi."


def test_timeout_message_when_command_exceeds_limit() -> None:
    @dataclass
    class SlowAgent(FakeAgentService):
        async def status(self, actor: str) -> ServiceResult:
            await asyncio.sleep(0.2)
            return ServiceResult(ok=True, message="slow")

    bot, _, _, _ = build_bot(timeout_seconds=0.05)
    bot.agent_service = SlowAgent()
    result = asyncio.run(bot.handle_text(chat_id="100", text="/status", actor="user:100"))
    assert result == TIMEOUT_MESSAGE


def test_approve_flow_calls_order_service_after_totp() -> None:
    bot, _, order, _ = build_bot()
    prompt = asyncio.run(bot.handle_text(chat_id="100", text="/approve ord-1", actor="user:100"))
    assert prompt == "Conferma con codice TOTP"
    done = asyncio.run(bot.handle_text(chat_id="100", text="123456", actor="user:100"))
    assert "approved ord-1" in done
    assert order.approved == ["ord-1"]
