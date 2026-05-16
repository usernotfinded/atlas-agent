from __future__ import annotations

from typing import Any

from atlas_agent.redaction import (
    REDACTED_VALUE,
    SECRET_MARKERS,
    RedactionEngine,
    default_redaction_engine,
    refresh_redaction_secrets,
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
