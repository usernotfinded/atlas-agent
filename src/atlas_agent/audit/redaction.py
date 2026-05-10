from __future__ import annotations

import os
from typing import Any
from atlas_agent.config.secrets import is_secret_key


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

REDACTED_VALUE = "[REDACTED]"


def get_known_secrets() -> set[str]:
    """Collect all known active secret values from environment."""
    secrets = set()
    for k, v in os.environ.items():
        if is_secret_key(k) and v and len(v) >= 4:
            secrets.add(v)
    return secrets


def redact_text(text: str) -> str:
    """Redact known secret values from a free text string."""
    if not isinstance(text, str):
        return text
    secrets = get_known_secrets()
    for s in secrets:
        text = text.replace(s, REDACTED_VALUE)
    return text


def redact_payload(payload: Any) -> Any:
    """
    Recursively redact keys containing sensitive markers, and redact known secrets from free text.
    """
    if isinstance(payload, dict):
        redacted: dict[str, Any] = {}
        for key, value in payload.items():
            key_text = str(key).upper()
            if any(marker in key_text for marker in SECRET_MARKERS):
                redacted[key] = REDACTED_VALUE
            else:
                redacted[key] = redact_payload(value)
        return redacted
    if isinstance(payload, list | tuple):
        return [redact_payload(item) for item in payload]
    if isinstance(payload, str):
        return redact_text(payload)
    return payload

