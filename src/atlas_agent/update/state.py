# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    update/state.py
# PURPOSE: Remembers when we last checked for an update, so the check does not run
#          on every single command.
# DEPS:    stdlib only
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


# --- CONFIGURATIONS & CONSTANTS ---

# Note what is absent: there is no "auto-apply" value here. Checking is automatic;
# INSTALLING never is. Self-updating code without being asked is not a feature.
AUTO_CHECK_VALUES = frozenset({"off", "daily", "weekly"})


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass
class UpdateState:
    current_version: str
    last_checked_at: str | None = None
    latest_version: str | None = None
    latest_source: str | None = None
    last_update_attempt_at: str | None = None
    last_successful_update_at: str | None = None
    previous_version: str | None = None
    previous_git_commit: str | None = None
    rollback_available: bool = False
    auto_apply_enabled: bool = False
    auto_check_schedule: str = "off"
    latest_notes: str | None = None
    backup_path: str | None = None
    last_error: str | None = None

    @classmethod
    def create_default(cls, *, current_version: str) -> UpdateState:
        return cls(current_version=current_version, latest_version=current_version)

    @classmethod
    def from_dict(
        cls,
        payload: dict[str, Any],
        *,
        current_version: str,
    ) -> UpdateState:
        state = cls(
            current_version=str(payload.get("current_version") or current_version),
            last_checked_at=_optional_str(payload.get("last_checked_at")),
            latest_version=_optional_str(payload.get("latest_version")),
            latest_source=_optional_str(payload.get("latest_source")),
            last_update_attempt_at=_optional_str(payload.get("last_update_attempt_at")),
            last_successful_update_at=_optional_str(payload.get("last_successful_update_at")),
            previous_version=_optional_str(payload.get("previous_version")),
            previous_git_commit=_optional_str(payload.get("previous_git_commit")),
            rollback_available=bool(payload.get("rollback_available", False)),
            auto_apply_enabled=bool(payload.get("auto_apply_enabled", False)),
            auto_check_schedule=_normalize_auto_check(payload.get("auto_check_schedule", "off")),
            latest_notes=_optional_str(payload.get("latest_notes")),
            backup_path=_optional_str(payload.get("backup_path")),
            last_error=_optional_str(payload.get("last_error")),
        )
        state.current_version = current_version
        if not state.latest_version:
            state.latest_version = current_version
        return state

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["auto_check_schedule"] = _normalize_auto_check(self.auto_check_schedule)
        return payload


class UpdateStateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self, *, current_version: str) -> UpdateState:
        if not self.path.exists():
            return UpdateState.create_default(current_version=current_version)
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return UpdateState.create_default(current_version=current_version)
        if not isinstance(raw, dict):
            return UpdateState.create_default(current_version=current_version)
        return UpdateState.from_dict(raw, current_version=current_version)

    def save(self, state: UpdateState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    as_str = str(value).strip()
    return as_str or None


def _normalize_auto_check(value: Any) -> str:
    candidate = str(value or "off").strip().lower()
    if candidate not in AUTO_CHECK_VALUES:
        return "off"
    return candidate
