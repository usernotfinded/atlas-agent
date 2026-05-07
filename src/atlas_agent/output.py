from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


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


def emit_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True))
