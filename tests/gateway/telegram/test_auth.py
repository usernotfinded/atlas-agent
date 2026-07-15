# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/gateway/telegram/test_auth.py
# PURPOSE: Verifies auth behavior and regression expectations.
# DEPS:    dataclasses, datetime, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from atlas_agent.gateway.telegram.auth import TelegramAuth, TelegramAuthConfig


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

@dataclass
class FakeKeyring:
    store: dict[tuple[str, str], str]

    def get_password(self, service_name: str, username: str) -> str | None:
        return self.store.get((service_name, username))

    def set_password(self, service_name: str, username: str, password: str) -> None:
        self.store[(service_name, username)] = password


class FakeTotp:
    def random_base32(self) -> str:
        return "TESTSECRET"

    def verify(self, secret: str, code: str, *, valid_window: int = 1) -> bool:
        return secret == "TESTSECRET" and code.strip() == "123456"


def build_auth(*, allowed: tuple[str, ...] = ("100", "101")) -> TelegramAuth:
    return TelegramAuth(
        config=TelegramAuthConfig(
            allowed_users=frozenset(allowed),
            keyring_service="atlas-test-telegram",
            challenge_ttl_seconds=60,
            challenge_max_attempts=2,
            totp_valid_window=1,
        ),
        keyring_backend=FakeKeyring(store={}),
        totp_backend=FakeTotp(),
    )


def test_authorized_user_whitelist() -> None:
    auth = build_auth()

    assert auth.is_authorized("100")
    assert auth.is_authorized(101)
    assert not auth.is_authorized("999")


def test_totp_secret_is_persisted_in_keyring() -> None:
    keyring = FakeKeyring(store={})
    auth = TelegramAuth(
        config=TelegramAuthConfig(
            allowed_users=frozenset({"100"}),
            keyring_service="atlas-test-telegram",
        ),
        keyring_backend=keyring,
        totp_backend=FakeTotp(),
    )

    first = auth.ensure_totp_secret("100")
    second = auth.ensure_totp_secret("100")

    assert first == "TESTSECRET"
    assert second == "TESTSECRET"
    assert len(keyring.store) == 1


def test_challenge_success_consumes_pending_state() -> None:
    auth = build_auth()
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    auth.start_challenge(
        chat_id="100",
        command="/kill flatten",
        actor="user:100",
        payload={"mode": "flatten"},
        now=now,
    )
    assert auth.has_pending_challenge("100", now=now)

    result = auth.verify_challenge(chat_id="100", code="123456", now=now)
    assert result.ok
    assert result.challenge is not None
    assert result.challenge.command == "/kill flatten"
    assert result.challenge.payload["mode"] == "flatten"
    assert not auth.has_pending_challenge("100", now=now)


def test_challenge_invalid_code_expires_after_max_attempts() -> None:
    auth = build_auth()
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    auth.start_challenge(chat_id="100", command="/approve a", actor="user:100", now=now)

    first = auth.verify_challenge(chat_id="100", code="111111", now=now)
    assert not first.ok
    assert first.reason == "invalid code"
    assert auth.has_pending_challenge("100", now=now)

    second = auth.verify_challenge(chat_id="100", code="111111", now=now)
    assert not second.ok
    assert second.reason == "invalid code: attempts exceeded"
    assert not auth.has_pending_challenge("100", now=now)


def test_challenge_expiration() -> None:
    auth = build_auth()
    start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    auth.start_challenge(chat_id="100", command="/resume", actor="user:100", now=start)

    later = start + timedelta(seconds=120)
    result = auth.verify_challenge(chat_id="100", code="123456", now=later)
    assert not result.ok
    assert result.reason == "challenge expired"


def test_confirmation_message_contract() -> None:
    auth = build_auth()
    assert auth.confirmation_message() == "Conferma con codice TOTP"
