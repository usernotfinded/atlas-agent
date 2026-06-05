"""Local notification record storage.

Stores notification delivery results as JSON artifacts under
`.atlas/notifications/` for audit and review.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from atlas_agent.notifications.models import NotificationResult
from atlas_agent.notifications.redaction import redact_result


NOTIFICATIONS_DIR = ".atlas/notifications"


def _notifications_path(workspace: str | Path = ".") -> Path:
    return Path(workspace) / NOTIFICATIONS_DIR


def save_result(
    result: NotificationResult,
    workspace: str | Path = ".",
) -> Path:
    """Persist a redacted notification result to local storage."""
    notifications_dir = _notifications_path(workspace)
    notifications_dir.mkdir(parents=True, exist_ok=True)
    path = notifications_dir / f"{result.notification_id}.json"
    redacted = redact_result(result)
    path.write_text(
        json.dumps(redacted, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path


def list_results(
    workspace: str | Path = ".",
) -> list[dict[str, Any]]:
    """List notification result metadata, newest first."""
    notifications_dir = _notifications_path(workspace)
    if not notifications_dir.exists():
        return []

    results: list[dict[str, Any]] = []
    for path in sorted(notifications_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            results.append(
                {
                    "notification_id": data.get("notification_id", ""),
                    "transport": data.get("transport", ""),
                    "status": data.get("status", ""),
                    "timestamp": data.get("timestamp", ""),
                    "path": str(path.resolve().relative_to(Path(workspace).resolve())),
                }
            )
        except (json.JSONDecodeError, Exception):
            continue
    return results


def load_result(
    notification_id: str,
    workspace: str | Path = ".",
) -> dict[str, Any] | None:
    """Load a single notification result by ID."""
    path = _notifications_path(workspace) / f"{notification_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception):
        return None
