from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import os
import threading
from typing import Any, Protocol


TOTP_CONFIRMATION_MESSAGE = "Conferma con codice TOTP"


class KeyringBackend(Protocol):
    def get_password(self, service_name: str, username: str) -> str | None:
        ...

    def set_password(self, service_name: str, username: str, password: str) -> None:
        ...


class TotpBackend(Protocol):
    def random_base32(self) -> str:
        ...

    def verify(self, secret: str, code: str, *, valid_window: int = 1) -> bool:
        ...


@dataclass(frozen=True)
class TelegramAuthConfig:
    allowed_users: frozenset[str]
    keyring_service: str = "atlas-agent-telegram"
    challenge_ttl_seconds: int = 120
    challenge_max_attempts: int = 3
    totp_valid_window: int = 1

    @classmethod
    def from_env(cls) -> TelegramAuthConfig:
        allowed_raw = os.getenv("ATLAS_TELEGRAM_ALLOWED_USERS") or os.getenv(
            "TELEGRAM_ALLOWED_USER_IDS",
            "",
        )
        allowed_users = frozenset(
            part.strip() for part in allowed_raw.split(",") if part.strip()
        )
        challenge_ttl_raw = os.getenv("ATLAS_TELEGRAM_TOTP_CHALLENGE_TTL_SECONDS", "").strip()
        challenge_ttl_seconds = int(challenge_ttl_raw) if challenge_ttl_raw else 120
        max_attempts_raw = os.getenv("ATLAS_TELEGRAM_TOTP_MAX_ATTEMPTS", "").strip()
        challenge_max_attempts = int(max_attempts_raw) if max_attempts_raw else 3
        keyring_service = os.getenv("ATLAS_TELEGRAM_KEYRING_SERVICE", "atlas-agent-telegram").strip()
        totp_window_raw = os.getenv("ATLAS_TELEGRAM_TOTP_VALID_WINDOW", "").strip()
        totp_valid_window = int(totp_window_raw) if totp_window_raw else 1
        if challenge_ttl_seconds <= 0:
            raise ValueError("ATLAS_TELEGRAM_TOTP_CHALLENGE_TTL_SECONDS must be positive")
        if challenge_max_attempts <= 0:
            raise ValueError("ATLAS_TELEGRAM_TOTP_MAX_ATTEMPTS must be positive")
        if totp_valid_window < 0:
            raise ValueError("ATLAS_TELEGRAM_TOTP_VALID_WINDOW cannot be negative")
        if not keyring_service:
            raise ValueError("ATLAS_TELEGRAM_KEYRING_SERVICE cannot be empty")
        return cls(
            allowed_users=allowed_users,
            keyring_service=keyring_service,
            challenge_ttl_seconds=challenge_ttl_seconds,
            challenge_max_attempts=challenge_max_attempts,
            totp_valid_window=totp_valid_window,
        )


@dataclass(frozen=True)
class PendingChallenge:
    chat_id: str
    command: str
    actor: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    expires_at: str = ""
    attempts: int = 0

    def is_expired(self, now: datetime) -> bool:
        expires = datetime.fromisoformat(self.expires_at)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        return now >= expires


@dataclass(frozen=True)
class ChallengeVerification:
    ok: bool
    reason: str
    challenge: PendingChallenge | None = None


class TelegramAuth:
    def __init__(
        self,
        *,
        config: TelegramAuthConfig | None = None,
        keyring_backend: KeyringBackend | None = None,
        totp_backend: TotpBackend | None = None,
    ) -> None:
        self.config = config or TelegramAuthConfig.from_env()
        self._keyring = keyring_backend or _SystemKeyringBackend()
        self._totp = totp_backend or _PyotpBackend()
        self._lock = threading.RLock()
        self._challenges: dict[str, PendingChallenge] = {}

    def is_authorized(self, chat_id: str | int) -> bool:
        requested = str(chat_id).strip()
        return requested in self.config.allowed_users

    def ensure_totp_secret(self, chat_id: str | int) -> str:
        key = _secret_key(chat_id)
        with self._lock:
            secret = self._keyring.get_password(self.config.keyring_service, key)
            if secret:
                return secret
            secret = self._totp.random_base32()
            self._keyring.set_password(self.config.keyring_service, key, secret)
            return secret

    def start_challenge(
        self,
        *,
        chat_id: str | int,
        command: str,
        actor: str,
        payload: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> PendingChallenge:
        effective_now = now or datetime.now(UTC)
        self.ensure_totp_secret(chat_id)
        expires = effective_now + timedelta(seconds=self.config.challenge_ttl_seconds)
        challenge = PendingChallenge(
            chat_id=str(chat_id).strip(),
            command=command,
            actor=actor,
            payload=dict(payload or {}),
            created_at=effective_now.isoformat(),
            expires_at=expires.isoformat(),
            attempts=0,
        )
        with self._lock:
            self._challenges[challenge.chat_id] = challenge
        return challenge

    def has_pending_challenge(self, chat_id: str | int, *, now: datetime | None = None) -> bool:
        effective_now = now or datetime.now(UTC)
        with self._lock:
            challenge = self._challenges.get(str(chat_id).strip())
            if challenge is None:
                return False
            if challenge.is_expired(effective_now):
                self._challenges.pop(challenge.chat_id, None)
                return False
            return True

    def verify_challenge(
        self,
        *,
        chat_id: str | int,
        code: str,
        now: datetime | None = None,
    ) -> ChallengeVerification:
        effective_now = now or datetime.now(UTC)
        chat_key = str(chat_id).strip()
        with self._lock:
            challenge = self._challenges.get(chat_key)
            if challenge is None:
                return ChallengeVerification(False, "no pending challenge")
            if challenge.is_expired(effective_now):
                self._challenges.pop(chat_key, None)
                return ChallengeVerification(False, "challenge expired")
            secret = self.ensure_totp_secret(chat_key)
            verified = self._totp.verify(
                secret,
                code,
                valid_window=self.config.totp_valid_window,
            )
            if verified:
                self._challenges.pop(chat_key, None)
                return ChallengeVerification(True, "ok", challenge=challenge)

            next_attempts = challenge.attempts + 1
            if next_attempts >= self.config.challenge_max_attempts:
                self._challenges.pop(chat_key, None)
                return ChallengeVerification(False, "invalid code: attempts exceeded")
            updated = PendingChallenge(
                chat_id=challenge.chat_id,
                command=challenge.command,
                actor=challenge.actor,
                payload=challenge.payload,
                created_at=challenge.created_at,
                expires_at=challenge.expires_at,
                attempts=next_attempts,
            )
            self._challenges[chat_key] = updated
            return ChallengeVerification(False, "invalid code")

    def cancel_challenge(self, chat_id: str | int) -> None:
        with self._lock:
            self._challenges.pop(str(chat_id).strip(), None)

    def confirmation_message(self) -> str:
        return TOTP_CONFIRMATION_MESSAGE


class _SystemKeyringBackend:
    def __init__(self) -> None:
        try:
            import keyring
        except ModuleNotFoundError as exc:
            raise RuntimeError("keyring package is required for Telegram 2FA") from exc
        self._keyring = keyring

    def get_password(self, service_name: str, username: str) -> str | None:
        return self._keyring.get_password(service_name, username)

    def set_password(self, service_name: str, username: str, password: str) -> None:
        self._keyring.set_password(service_name, username, password)


class _PyotpBackend:
    def __init__(self) -> None:
        try:
            import pyotp
        except ModuleNotFoundError as exc:
            raise RuntimeError("pyotp package is required for Telegram 2FA") from exc
        self._pyotp = pyotp

    def random_base32(self) -> str:
        return str(self._pyotp.random_base32())

    def verify(self, secret: str, code: str, *, valid_window: int = 1) -> bool:
        normalized = "".join(ch for ch in code.strip() if ch.isdigit())
        if not normalized:
            return False
        totp = self._pyotp.TOTP(secret)
        return bool(totp.verify(normalized, valid_window=valid_window))


def _secret_key(chat_id: str | int) -> str:
    return f"chat:{str(chat_id).strip()}"

