# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    gateway/telegram/__init__.py
# PURPOSE: Public surface of the Telegram control plane.
# DEPS:    gateway.telegram.auth, .bot, .ratelimit, .sanitize, .config, .server
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from atlas_agent.gateway.telegram.auth import (
    KeyringBackend,
    PendingChallenge,
    TelegramAuth,
    TelegramAuthConfig,
    TotpBackend,
)
from atlas_agent.gateway.telegram.ratelimit import (
    RateLimitConfig,
    RateLimitDecision,
    TelegramRateLimiter,
)
from atlas_agent.gateway.telegram.config import (
    TelegramWebhookSettings,
    load_telegram_settings,
)
from atlas_agent.gateway.telegram.sanitize import safe_output, sanitize_output
from atlas_agent.gateway.telegram.server import TelegramWebhookServer, create_fastapi_app

__all__ = [
    "KeyringBackend",
    "PendingChallenge",
    "RateLimitConfig",
    "RateLimitDecision",
    "TelegramWebhookServer",
    "TelegramAuth",
    "TelegramAuthConfig",
    "TelegramRateLimiter",
    "TelegramWebhookSettings",
    "TotpBackend",
    "create_fastapi_app",
    "load_telegram_settings",
    "safe_output",
    "sanitize_output",
]
