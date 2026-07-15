# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/gateway/telegram/test_server.py
# PURPOSE: Verifies server behavior and regression expectations.
# DEPS:    dataclasses, fastapi, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi.testclient import TestClient

from atlas_agent.gateway.services import ServiceResult
from atlas_agent.gateway.telegram.auth import TelegramAuth, TelegramAuthConfig
from atlas_agent.gateway.telegram.bot import TelegramBotConfig, TelegramCommandBot
from atlas_agent.gateway.telegram.config import TelegramWebhookSettings
from atlas_agent.gateway.telegram.ratelimit import RateLimitConfig, TelegramRateLimiter
from atlas_agent.gateway.telegram.server import create_fastapi_app


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

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
        self.entries.append({"chat_id": chat_id, "command": command, "outcome": outcome})


@dataclass
class FakeAgentService:
    async def status(self, actor: str) -> ServiceResult:
        return ServiceResult(ok=True, message="status ok")

    async def plan(self, actor: str) -> ServiceResult:
        return ServiceResult(ok=True, message="plan ok")

    async def run(self, actor: str, mode: str = "auto") -> ServiceResult:
        return ServiceResult(ok=True, message=f"run {mode}")

    async def learn(self, actor: str) -> ServiceResult:
        return ServiceResult(ok=True, message="learn ok")

    async def reflect(self, actor: str) -> ServiceResult:
        return ServiceResult(ok=True, message="reflect ok")

    async def positions(self, actor: str) -> ServiceResult:
        return ServiceResult(ok=True, message="positions ok")

    async def memory_search(self, actor: str, query: str) -> ServiceResult:
        return ServiceResult(ok=True, message=f"memory {query}")

    async def skills(self, actor: str) -> ServiceResult:
        return ServiceResult(ok=True, message="skills ok")


@dataclass
class FakeOrderService:
    async def pending(self, actor: str) -> ServiceResult:
        return ServiceResult(ok=True, message="pending ok")

    async def approve(self, actor: str, order_id: str) -> ServiceResult:
        return ServiceResult(ok=True, message=f"approved {order_id}")

    async def reject(self, actor: str, order_id: str) -> ServiceResult:
        return ServiceResult(ok=True, message=f"rejected {order_id}")


@dataclass
class FakeKillSwitchService:
    async def kill(self, actor: str, mode: str = "soft", reason: str = "") -> ServiceResult:
        return ServiceResult(ok=True, message=f"kill {mode}")

    async def resume(self, actor: str) -> ServiceResult:
        return ServiceResult(ok=True, message="resumed")

    async def heartbeat(self, actor: str, source: str = "telegram") -> ServiceResult:
        return ServiceResult(ok=True, message="heartbeat")

    async def status(self, actor: str) -> ServiceResult:
        return ServiceResult(ok=True, message="kill status")


def make_client() -> TestClient:
    auth = TelegramAuth(
        config=TelegramAuthConfig(
            allowed_users=frozenset({"100"}),
            keyring_service="atlas-test-telegram",
        ),
        keyring_backend=FakeKeyring(),
        totp_backend=FakeTotp(),
    )
    bot = TelegramCommandBot(
        auth=auth,
        rate_limiter=TelegramRateLimiter(config=RateLimitConfig()),
        agent_service=FakeAgentService(),
        order_service=FakeOrderService(),
        kill_switch_service=FakeKillSwitchService(),
        audit_service=FakeAudit(),
        config=TelegramBotConfig(command_timeout_seconds=1.0),
    )
    app = create_fastapi_app(
        bot=bot,
        settings=TelegramWebhookSettings(
            webhook_path="/telegram/hook",
            webhook_secret_token="secret-123",
            healthz_path="/healthz",
        ),
    )
    return TestClient(app)


def test_healthz_endpoint() -> None:
    client = make_client()
    response = client.get("/healthz")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["service"] == "atlas-telegram-webhook"
    assert "ts_utc" in payload


def test_webhook_rejects_invalid_secret_header() -> None:
    client = make_client()
    response = client.post(
        "/telegram/hook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        json={"message": {"chat": {"id": 100}, "from": {"id": 100}, "text": "/status"}},
    )
    assert response.status_code == 403


def test_webhook_dispatches_valid_update() -> None:
    client = make_client()
    response = client.post(
        "/telegram/hook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret-123"},
        json={"message": {"chat": {"id": 100}, "from": {"id": 100}, "text": "/status"}},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["handled"] is True
    assert payload["chat_id"] == "100"
    assert "status ok" in payload["response"]


def test_webhook_ignores_non_message_updates() -> None:
    client = make_client()
    response = client.post(
        "/telegram/hook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret-123"},
        json={"callback_query": {"id": "x"}},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["handled"] is False
