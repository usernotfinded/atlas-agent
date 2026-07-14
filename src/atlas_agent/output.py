# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    output.py
# PURPOSE: The canonical shape of every JSON answer the CLI emits. Every command
#          wraps its payload in one of these two envelopes, so machine consumers
#          can branch on `ok` before touching anything else.
# DEPS:    stdlib only (json, datetime) — deliberately dependency-free so the
#          envelope stays importable from the configless bootstrap paths.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any


# ==============================================================================
# TIMESTAMPS
# ==============================================================================

def now_iso() -> str:
    # Second-level precision, always UTC: these timestamps land in audit records
    # that get diffed across machines, and microseconds only add spurious churn.
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# ==============================================================================
# RESPONSE ENVELOPES
# ==============================================================================

def success_envelope(command: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "command": command,
        "generated_at": now_iso(),
        "data": data,
    }


def error_envelope(
    command: str,
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "command": command,
        "generated_at": now_iso(),
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
    }


# ==============================================================================
# EMISSION
# ==============================================================================

def emit_json(payload: dict[str, Any]) -> None:
    # sort_keys is not cosmetic: the checkers and the release-assurance bundles
    # diff CLI output byte-for-byte, so key order has to be deterministic.
    print(json.dumps(payload, sort_keys=True))
