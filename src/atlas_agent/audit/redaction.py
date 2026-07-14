# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    audit/redaction.py
# PURPOSE: Re-exports the central redaction engine under the audit namespace.
#          A thin facade on purpose: there is exactly ONE redaction implementation
#          in this project, and an audit-local copy would be the one that drifts
#          and starts leaking.
# DEPS:    atlas_agent.redaction (the single implementation)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from typing import Any

from atlas_agent.redaction import (
    REDACTED_VALUE,
    SECRET_MARKERS,
    RedactionEngine,
    default_redaction_engine,
    refresh_redaction_secrets,
)


# ==============================================================================
# PUBLIC API (delegating facade)
# ==============================================================================

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
