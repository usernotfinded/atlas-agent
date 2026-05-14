from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from atlas_agent.safety.secrets import scan_text_for_secrets


REQUIRED_EVENT_FIELDS = (
    "timestamp",
    "event_type",
    "run_id",
    "command",
    "mode",
    "payload",
)

KNOWN_EVENT_TYPES = {
    "agent_started",
    "market_state_detected",
    "memory_loaded",
    "research_completed",
    "model_guidance_loaded",
    "decision_proposed",
    "risk_approved",
    "risk_rejected",
    "order_created",
    "order_pending_approval",
    "order_executed",
    "order_rejected",
    "memory_updated",
    "skill_proposed",
    "skill_improved",
    "reflection_written",
    "notification_sent",
    "git_sync_completed",
    "agent_completed",
    "agent_failed",
    "run_once_live_disabled",
    "run_once_live_sync_started",
    "run_once_live_sync_failed",
    "run_once_live_risk_evaluated",
    "run_once_live_analysis_only",
    "run_once_live_rejected",
}

LIKELY_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{10,}\b", flags=re.IGNORECASE),
    re.compile(r"\bpplx-[A-Za-z0-9_-]{10,}\b", flags=re.IGNORECASE),
    re.compile(r"\bxox(?:b|a|p|r)-[A-Za-z0-9_-]{10,}\b", flags=re.IGNORECASE),
    re.compile(r"\bakia[A-Za-z0-9]{10,}\b", flags=re.IGNORECASE),
    re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]{10,}", flags=re.IGNORECASE),
)


def validate_event_record(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_EVENT_FIELDS:
        if field not in record:
            errors.append(f"missing field: {field}")
    if errors:
        return errors

    timestamp = record.get("timestamp")
    if not isinstance(timestamp, str):
        errors.append("timestamp must be a string")
    else:
        try:
            datetime.fromisoformat(timestamp)
        except ValueError:
            errors.append("timestamp is not valid ISO-8601")

    event_type = record.get("event_type")
    if not isinstance(event_type, str) or not event_type:
        errors.append("event_type must be a non-empty string")
    elif event_type not in KNOWN_EVENT_TYPES:
        errors.append(f"unknown event_type: {event_type}")

    run_id = record.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        errors.append("run_id must be a non-empty string")

    command = record.get("command")
    if not isinstance(command, str) or not command.strip():
        errors.append("command must be a non-empty string")

    mode = record.get("mode")
    if not isinstance(mode, str) or not mode.strip():
        errors.append("mode must be a non-empty string")

    if not isinstance(record.get("payload"), dict):
        errors.append("payload must be an object")

    return errors


def find_likely_secrets(value: Any) -> list[str]:
    findings: list[str] = []
    _scan(value, findings)
    # keep unique while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for item in findings:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def _scan(value: Any, findings: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).lower()
            if any(marker in key_text for marker in ("token", "secret", "password", "api_key")):
                if isinstance(item, str) and item and item != "[REDACTED]":
                    findings.append(f"{key}: non-redacted value")
            _scan(item, findings)
        return
    if isinstance(value, list | tuple):
        for item in value:
            _scan(item, findings)
        return
    if not isinstance(value, str):
        return
    if scan_text_for_secrets(value):
        findings.append("inline secret assignment")
    for pattern in LIKELY_SECRET_PATTERNS:
        if pattern.search(value):
            findings.append("likely token pattern")
            break
