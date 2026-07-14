# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    events/schema.py
# PURPOSE: Validates an event record before it is written. Two jobs: keep the trail
#          structurally sound (so replay never chokes on it), and act as the LAST
#          secret check before anything hits disk.
# DEPS:    safety.secrets (the leak scanner)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from atlas_agent.safety.secrets import scan_text_for_secrets


# --- CONFIGURATIONS & CONSTANTS ---

# All six are mandatory. `run_id` in particular: an event without one cannot be tied to
# a run, and an untraceable event is not evidence of anything.
REQUIRED_EVENT_FIELDS = (
    "timestamp",
    "event_type",
    "run_id",
    "command",
    "mode",
    "payload",
)

# A closed set. An event type not listed here is REJECTED — which means adding a new
# kind of event is a deliberate act that shows up in a diff, not something a stray
# call site can do silently. The trail is only complete if its vocabulary is known.
KNOWN_EVENT_TYPES = {
    "agent_started",
    "market_state_detected",
    "memory_loaded",
    "research_completed",
    "research_plan_created",
    "research_run_created",
    "research_verification_created",
    "research_evaluation_created",
    "research_prompt_packet_created",
    "research_provider_response_created",
    "research_response_review_created",
    "research_dossier_created",
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
    "autonomous_paper_started",
    "autonomous_paper_completed",
}

LIKELY_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{10,}\b", flags=re.IGNORECASE),
    re.compile(r"\bpplx-[A-Za-z0-9_-]{10,}\b", flags=re.IGNORECASE),
    re.compile(r"\bxox(?:b|a|p|r)-[A-Za-z0-9_-]{10,}\b", flags=re.IGNORECASE),
    re.compile(r"\bakia[A-Za-z0-9]{10,}\b", flags=re.IGNORECASE),
    re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]{10,}", flags=re.IGNORECASE),
)


# ==============================================================================
# VALIDATION
# ==============================================================================

def validate_event_record(record: dict[str, Any]) -> list[str]:
    """Check an event record. Returns a list of problems — empty means valid.

    Returns:
        Every error found, not just the first, so a caller fixing a malformed event
        sees the whole picture in one go.
    """
    errors: list[str] = []
    for field in REQUIRED_EVENT_FIELDS:
        if field not in record:
            errors.append(f"missing field: {field}")
    # Early return: with a field missing there is nothing to type-check below, and the
    # follow-on errors would be noise obscuring the real one.
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


# ==============================================================================
# LEAK DETECTION
# ==============================================================================
#
# The safety net UNDER the redaction engine. By the time a record gets here it has
# already been scrubbed twice (see EventLogger.write), so anything this finds is a
# bug in redaction — which is exactly why it is worth checking. A detector that only
# ever fires when the primary defence has already failed is doing its job.

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
    # Recurses through nested structures, because a secret buried three levels down in
    # a broker's response payload is still a secret on disk.
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).lower()
            if any(marker in key_text for marker in ("token", "secret", "password", "api_key")):
                # The check is "was this redacted?", not "does this look like a key?".
                # A secret-named field holding anything OTHER than the redaction marker
                # means the scrubber missed it.
                # Only the KEY name is reported — never the value, or the report would
                # leak the very thing it is flagging.
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
