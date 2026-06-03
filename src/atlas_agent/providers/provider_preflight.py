"""Provider preflight dry-run call-plan artifact generator.

This module generates a local-only, dry-run provider call-plan artifact.
It does NOT:
  - Make network calls
  - Read API keys or credentials
  - Load .env.atlas
  - Import provider SDKs (openai, anthropic, etc.)
  - Call any provider
  - Touch broker adapters
  - Enable live trading
  - Create pending orders or approvals

The artifact is purely informational and does not authorize any provider
execution. All safety flags are set to False.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------

_MAX_PROVIDER_ID_LEN = 64
_MAX_MODEL_ID_LEN = 128
_MAX_PURPOSE_LEN = 128
_MIN_CONTEXT_CHARS = 1
_MAX_CONTEXT_CHARS = 200_000

# Matches control characters (except common whitespace), absolute paths,
# and common secret-like fragments.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ABSOLUTE_PATH_RE = re.compile(r"(?:^|[\s])(?:/[^\s]+|[A-Z]:\\[^\s]+)")
_SECRET_FRAGMENT_RE = re.compile(
    r"(?:api[_-]?key|secret|token|password|bearer|authorization|credential)",
    re.IGNORECASE,
)
_NEWLINE_RE = re.compile(r"[\r\n]")

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


class PreflightValidationError(ValueError):
    """Raised when a preflight input fails validation."""


def _validate_bounded_string(
    value: str,
    field_name: str,
    *,
    max_len: int,
) -> str:
    """Validate a bounded string input.

    Rejects empty strings, strings exceeding *max_len*, strings containing
    control characters, newlines, absolute paths, or secret-like fragments.
    """
    if not isinstance(value, str):
        raise PreflightValidationError(
            f"{field_name}: must be a string"
        )
    if not value or not value.strip():
        raise PreflightValidationError(
            f"{field_name}: must not be empty"
        )
    if len(value) > max_len:
        raise PreflightValidationError(
            f"{field_name}: exceeds maximum length of {max_len} characters"
        )
    if _CONTROL_CHAR_RE.search(value):
        raise PreflightValidationError(
            f"{field_name}: contains forbidden control characters"
        )
    if _NEWLINE_RE.search(value):
        raise PreflightValidationError(
            f"{field_name}: contains forbidden newline characters"
        )
    if _ABSOLUTE_PATH_RE.search(value):
        raise PreflightValidationError(
            f"{field_name}: contains forbidden absolute path"
        )
    if _SECRET_FRAGMENT_RE.search(value):
        raise PreflightValidationError(
            f"{field_name}: contains forbidden secret-like fragment"
        )
    return value.strip()


def validate_provider_id(value: str) -> str:
    """Validate provider_id: 1-64 chars, no control/newline/path/secret."""
    return _validate_bounded_string(
        value, "provider_id", max_len=_MAX_PROVIDER_ID_LEN
    )


def validate_model_id(value: str) -> str:
    """Validate model_id: 1-128 chars, no control/newline/path/secret."""
    return _validate_bounded_string(
        value, "model_id", max_len=_MAX_MODEL_ID_LEN
    )


def validate_purpose(value: str) -> str:
    """Validate purpose: 1-128 chars, no control/newline/path/secret."""
    return _validate_bounded_string(
        value, "purpose", max_len=_MAX_PURPOSE_LEN
    )


def validate_max_context_chars(value: int) -> int:
    """Validate max_context_chars: integer in [1, 200000]."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise PreflightValidationError(
            "max_context_chars: must be an integer"
        )
    if value < _MIN_CONTEXT_CHARS or value > _MAX_CONTEXT_CHARS:
        raise PreflightValidationError(
            f"max_context_chars: must be between {_MIN_CONTEXT_CHARS} "
            f"and {_MAX_CONTEXT_CHARS}"
        )
    return value


# ---------------------------------------------------------------------------
# Artifact generation
# ---------------------------------------------------------------------------


def _metadata_hash(provider_id: str, model_id: str, purpose: str) -> str:
    """Compute a SHA-256 hash of the call-plan metadata (not raw bodies)."""
    payload = json.dumps(
        {
            "provider_id": provider_id,
            "model_id": model_id,
            "purpose": purpose,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def generate_call_plan_artifact(
    *,
    provider_id: str,
    model_id: str,
    purpose: str,
    max_context_chars: int = 4000,
) -> dict[str, Any]:
    """Generate a dry-run provider call-plan artifact.

    Returns a dict suitable for JSON serialization. All safety flags are
    set to False. No provider call is made, no credentials are loaded,
    and no network is used.
    """
    # Validate all inputs
    provider_id = validate_provider_id(provider_id)
    model_id = validate_model_id(model_id)
    purpose = validate_purpose(purpose)
    max_context_chars = validate_max_context_chars(max_context_chars)

    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    metadata_hash = _metadata_hash(provider_id, model_id, purpose)

    return {
        "artifact_type": "provider_call_plan",
        "schema_version": 1,
        "created_at": now,
        "provider_id": provider_id,
        "model_id": model_id,
        "purpose": purpose,
        "max_context_chars": max_context_chars,
        "payload_shape": {
            "message_count_estimate": 0,
            "raw_body_stored": False,
            "body_hash_present": True,
        },
        "payload_minimization_summary": {
            "raw_prompt_body_stored": False,
            "raw_request_body_stored": False,
            "raw_response_body_stored": False,
            "hashes_only": True,
        },
        "payload_redaction_summary": {
            "secrets_redacted": True,
            "absolute_paths_redacted": True,
            "broker_credentials_redacted": True,
        },
        "safety_flags": {
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "outbound_request_sent": False,
            "response_received": False,
            "broker_touched": False,
            "live_trading_enabled": False,
            "pending_order_created": False,
            "order_approved": False,
            "payload_body_stored": False,
        },
        "request_hash": None,
        "response_hash": None,
        "metadata_hash": metadata_hash,
        "call_authorized": False,
        "manual_review_required": True,
        "notes": [
            "Dry-run artifact only.",
            "No provider call was made.",
            "No credentials were loaded.",
            "No network was used.",
        ],
    }
