# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    gateway/telegram/config.py
# PURPOSE: Settings for the Telegram webhook — the bot token, the secret header,
#          the allowed users.
# DEPS:    pydantic_settings (OPTIONAL — see the fallback below)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import os
from dataclasses import dataclass


# pydantic_settings is an optional dependency: the Telegram gateway is opt-in, and an
# install that never uses it should not have to carry the package. The fallback keeps
# `import atlas_agent` working without it.
try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ModuleNotFoundError:  # pragma: no cover - exercised by fallback tests/runtime
    BaseSettings = None  # type: ignore[assignment]
    SettingsConfigDict = None  # type: ignore[assignment]


if BaseSettings is not None:

    class TelegramWebhookSettings(BaseSettings):
        bot_token: str = ""
        webhook_path: str = "/telegram/webhook"
        webhook_secret_token: str = ""
        healthz_path: str = "/healthz"
        command_timeout_seconds: float = 30.0

        model_config = SettingsConfigDict(
            env_prefix="ATLAS_TELEGRAM_",
            extra="ignore",
        )

        def model_post_init(self, __context) -> None:
            _validate_paths(self.webhook_path, self.healthz_path)
            if self.command_timeout_seconds <= 0:
                raise ValueError("ATLAS_TELEGRAM_COMMAND_TIMEOUT_SECONDS must be positive")

else:

    @dataclass(frozen=True)
    class TelegramWebhookSettings:
        bot_token: str = ""
        webhook_path: str = "/telegram/webhook"
        webhook_secret_token: str = ""
        healthz_path: str = "/healthz"
        command_timeout_seconds: float = 30.0

        @classmethod
        def from_env(cls) -> TelegramWebhookSettings:
            timeout_raw = os.getenv("ATLAS_TELEGRAM_COMMAND_TIMEOUT_SECONDS", "").strip()
            timeout = float(timeout_raw) if timeout_raw else 30.0
            settings = cls(
                bot_token=os.getenv("ATLAS_TELEGRAM_BOT_TOKEN", ""),
                webhook_path=os.getenv("ATLAS_TELEGRAM_WEBHOOK_PATH", "/telegram/webhook"),
                webhook_secret_token=os.getenv("ATLAS_TELEGRAM_WEBHOOK_SECRET_TOKEN", ""),
                healthz_path=os.getenv("ATLAS_TELEGRAM_HEALTHZ_PATH", "/healthz"),
                command_timeout_seconds=timeout,
            )
            _validate_paths(settings.webhook_path, settings.healthz_path)
            if settings.command_timeout_seconds <= 0:
                raise ValueError("ATLAS_TELEGRAM_COMMAND_TIMEOUT_SECONDS must be positive")
            return settings


def load_telegram_settings() -> TelegramWebhookSettings:
    if BaseSettings is not None:
        return TelegramWebhookSettings()  # type: ignore[call-arg]
    return TelegramWebhookSettings.from_env()  # type: ignore[attr-defined]


def _validate_paths(webhook_path: str, healthz_path: str) -> None:
    for name, value in (("webhook_path", webhook_path), ("healthz_path", healthz_path)):
        if not value.startswith("/"):
            raise ValueError(f"{name} must start with '/'")
        if len(value.strip()) <= 1:
            raise ValueError(f"{name} cannot be root '/'")

