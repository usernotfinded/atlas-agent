from __future__ import annotations

from typing import Any


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


def redact_payload(payload: Any) -> Any:
    """
    Recursively redact keys containing sensitive markers.
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
    return payload
