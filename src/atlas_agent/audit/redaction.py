from __future__ import annotations

from typing import Any

from atlas_agent.redaction import (
    REDACTED_VALUE,
    RedactionEngine,
    default_redaction_engine,
    refresh_redaction_secrets,
)


SECRET_MARKERS = (
    "KEY",
    "API_KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "AUTHORIZATION",
    "AUTH",
    "BEARER",
    "COOKIE",
    "PRIVATE_KEY",
)


def get_known_secrets() -> set[str]:
    return default_redaction_engine().known_secrets


def redact_text(text: str) -> str:
    return default_redaction_engine().redact_text(text)


def redact_payload(payload: Any) -> Any:
    return default_redaction_engine().redact_payload(payload)


__all__ = [
    "REDACTED_VALUE",
    "RedactionEngine",
    "SECRET_MARKERS",
    "get_known_secrets",
    "redact_payload",
    "redact_text",
    "refresh_redaction_secrets",
]
