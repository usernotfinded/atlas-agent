"""Notification redaction helpers.

Redacts secrets from notification payloads and results before logging
or previewing. Never exposes webhook URLs or tokens.
"""
from __future__ import annotations

import re
from typing import Any

from atlas_agent.notifications.models import NotificationPayload, NotificationResult


# Patterns that indicate secret-like values
_SECRET_PATTERNS = [
    re.compile(r"https://hooks\.slack\.com/services/[^\s\"']+", re.IGNORECASE),
    re.compile(r"xox[baprs]-[a-zA-Z0-9-]+", re.IGNORECASE),
    re.compile(r"[a-zA-Z0-9_]+_API_KEY\s*[=:]\s*[^\s\"']+", re.IGNORECASE),
    re.compile(r"[a-zA-Z0-9_]+_TOKEN\s*[=:]\s*[^\s\"']+", re.IGNORECASE),
    re.compile(r"[a-zA-Z0-9_]+_SECRET\s*[=:]\s*[^\s\"']+", re.IGNORECASE),
    re.compile(r"[a-zA-Z0-9_]+_PASSWORD\s*[=:]\s*[^\s\"']+", re.IGNORECASE),
]

_REDACTION_MASK = "[REDACTED]"


def redact_text(text: str) -> str:
    """Redact known secret patterns from a string."""
    if not text:
        return text
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(_REDACTION_MASK, text)
    return text


def redact_payload(payload: NotificationPayload) -> dict[str, Any]:
    """Return a redacted dict of a notification payload."""
    data = payload.model_dump(mode="json")
    for key in ("message", "title", "metadata"):
        value = data.get(key)
        if isinstance(value, str):
            data[key] = redact_text(value)
        elif isinstance(value, dict):
            data[key] = {k: redact_text(v) if isinstance(v, str) else v for k, v in value.items()}
    return data


def redact_result(result: NotificationResult) -> dict[str, Any]:
    """Return a redacted dict of a notification result."""
    data = result.model_dump(mode="json")
    for key in ("message", "redacted_preview", "error_detail"):
        value = data.get(key)
        if isinstance(value, str):
            data[key] = redact_text(value)
    return data


def preview_payload(payload: NotificationPayload) -> str:
    """Create a short, redacted preview of a payload for dry-run display."""
    lines: list[str] = []
    lines.append(f"[{payload.severity.value.upper()}] {redact_text(payload.title)}")
    if payload.message:
        msg = payload.message[:500]
        if len(payload.message) > 500:
            msg += "..."
        lines.append(redact_text(msg))
    lines.append(f"source={payload.source} command={payload.source_command}")
    return "\n".join(lines)
