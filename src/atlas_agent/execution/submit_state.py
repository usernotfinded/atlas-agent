from __future__ import annotations

import copy
import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atlas_agent.execution.approval import (
    InvalidPendingOrderError,
    _compute_order_hash,
    _validate_v2_payload_integrity,
)


class SubmitStateError(Exception):
    """Raised for invalid submit-state transitions or arguments."""



# ---------------------------------------------------------------------------
# client_order_id generation
# ---------------------------------------------------------------------------

_MAX_CLIENT_ORDER_ID_LEN = 64
_CLIENT_ORDER_ID_SAFE_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def compute_client_order_id(order_id: str, order_hash: str) -> str:
    """Deterministic client_order_id derived from order id and hash.

    Format: atlas-{safe_order_id_prefix}-{hash_prefix}
    - safe_order_id_prefix: first 16 chars of order_id, with any disallowed chars replaced by '_'
    - hash_prefix: first 16 hex chars of order_hash
    - total max length: 5 + 16 + 1 + 16 = 38 chars (well under 64)
    """
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", order_id[:16])
    hash_prefix = order_hash[:16]
    result = f"atlas-{safe_id}-{hash_prefix}"
    if len(result) > _MAX_CLIENT_ORDER_ID_LEN:
        result = result[:_MAX_CLIENT_ORDER_ID_LEN]
    return result


# ---------------------------------------------------------------------------
# Read-only helpers
# ---------------------------------------------------------------------------

def load_pending_order(path: Path) -> dict[str, Any]:
    """Load, parse, and validate a pending order file.

    Returns the validated v2 payload dict. Raises InvalidPendingOrderError on
    malformed JSON, schema violations, or hash mismatch.
    """
    raw = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidPendingOrderError("invalid pending order file") from exc
    if not isinstance(payload, dict):
        raise InvalidPendingOrderError("pending order must be a JSON object")

    # Delegate full v2 integrity validation (schema + hash) to approval.py
    _validate_v2_payload_integrity(payload)
    return payload


def validate_pending_order_v2(payload: dict[str, Any]) -> None:
    """Validate that payload is a complete v2 pending order.

    Raises InvalidPendingOrderError on any failure.
    """
    _validate_v2_payload_integrity(payload)


def verify_order_hash(payload: dict[str, Any]) -> bool:
    """Return True if the stored order_hash matches the recomputed hash."""
    order = payload.get("order")
    if not isinstance(order, dict):
        return False
    stored_hash = payload.get("order_hash")
    if not isinstance(stored_hash, str) or not stored_hash:
        return False
    try:
        return stored_hash == _compute_order_hash(order)
    except Exception:
        return False


_BLOCKING_STATUSES = frozenset({
    "submit_uncertain",
    "reconciliation_required",
    "submitted",
    "duplicate_reconciled",
    "cancelled",
    "rejected",
    "expired",
})


def is_submit_blocked_by_state(payload: dict[str, Any]) -> tuple[bool, str | None]:
    """Return (blocked, reason) for the given pending order payload.

    A state is blocking if it indicates the order is already in flight,
    already completed, or requires explicit human reconciliation.
    """
    status = payload.get("status")
    if not isinstance(status, str):
        return True, "invalid status"
    if status in _BLOCKING_STATUSES:
        return True, status
    return False, None


# ---------------------------------------------------------------------------
# Atomic write helper
# ---------------------------------------------------------------------------

def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON atomically using write-to-temp + rename.

    On failure, the original file remains intact. No partial JSON writes survive.
    """
    tmp = path.with_suffix(f".tmp-{os.getpid()}")
    try:
        tmp.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp.replace(path)
    except OSError:
        # Attempt to clean up temp file on failure, but don't mask the original error
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Mutation helpers (all use atomic write)
# ---------------------------------------------------------------------------

def append_status_transition(
    path: Path,
    status: str,
    actor: str,
    *,
    reason: str | None = None,
    code: str | None = None,
) -> Path:
    """Append a status transition to the pending order file and update status.

    Returns the path to the updated file.
    """
    payload = load_pending_order(path)
    now = datetime.now(UTC).isoformat()
    transition: dict[str, Any] = {
        "status": status,
        "at": now,
        "actor": actor,
    }
    if reason is not None:
        transition["reason"] = reason
    if code is not None:
        transition["code"] = code
    payload["status"] = status
    payload["status_transitions"].append(transition)
    _atomic_write_json(path, payload)
    return path


def mark_reconciliation_required(path: Path, reason: str) -> Path:
    """Atomically mark the pending order as requiring reconciliation."""
    return append_status_transition(
        path,
        status="reconciliation_required",
        actor="system",
        reason=reason,
        code="reconcile_failed",
    )


def mark_duplicate_reconciled(
    path: Path,
    broker_order_id: str,
    broker_status: str,
) -> Path:
    """Atomically mark the pending order as duplicate-reconciled.

    Stores broker_order_id, broker_status, and reconciled_at.
    """
    payload = load_pending_order(path)
    now = datetime.now(UTC).isoformat()
    payload["status"] = "duplicate_reconciled"
    payload["broker_order_id"] = broker_order_id
    payload["broker_status"] = broker_status
    payload["reconciled_at"] = now
    payload["status_transitions"].append({
        "status": "duplicate_reconciled",
        "at": now,
        "actor": "reconcile:cli",
        "reason": f"broker_order_id={broker_order_id}",
    })
    _atomic_write_json(path, payload)
    return path


# ---------------------------------------------------------------------------
# client_order_id validation
# ---------------------------------------------------------------------------

def _validate_client_order_id(client_order_id: str | None) -> None:
    """Validate a client_order_id against Alpaca requirements.

    Raises SubmitStateError on any failure. Never includes the raw value
    in exception messages.
    """
    if not isinstance(client_order_id, str) or not client_order_id:
        raise SubmitStateError("invalid client_order_id")
    if len(client_order_id) > _MAX_CLIENT_ORDER_ID_LEN:
        raise SubmitStateError("invalid client_order_id")
    if not _CLIENT_ORDER_ID_SAFE_RE.fullmatch(client_order_id):
        raise SubmitStateError("invalid client_order_id")


# ---------------------------------------------------------------------------
# Submit attempt helpers
# ---------------------------------------------------------------------------

_SUBMIT_ATTEMPT_ALLOWED_KEYS = frozenset({
    "attempt_id",
    "client_order_id",
    "status",
    "created_at",
    "actor",
    "risk_revalidated",
    "sync_revalidated",
    "broker_order_id",
    "error_code",
})

_SUBMIT_ATTEMPT_REQUIRED_KEYS = frozenset({
    "attempt_id",
    "client_order_id",
    "status",
    "created_at",
    "actor",
})

_SUBMIT_ATTEMPT_STATUSES = frozenset({
    "prepared",
    "submit_requested",
    "acknowledged",
    "failed",
    "submit_uncertain",
    "submit_prepare_failed",
})

_SUBMIT_ACTORS = frozenset({
    "submit:cli",
    "system",
})

_SUBMIT_ATTEMPT_ERROR_CODES = frozenset({
    "broker_rejected_order",
    "broker_unavailable",
    "broker_transport_failed",
    "malformed_broker_response",
    "client_order_id_mismatch",
    "order_not_found",
    "unknown",
    "execution_broker_unavailable",
    "execution_broker_invalid",
})


def _validate_iso_datetime(value: Any, field_name: str = "datetime") -> None:
    """Validate that value is a valid ISO 8601 datetime string.

    Raises SubmitStateError with a static message (no raw value leak).
    """
    if not isinstance(value, str) or not value.strip():
        raise SubmitStateError(f"invalid {field_name}")
    try:
        datetime.fromisoformat(value)
    except ValueError:
        raise SubmitStateError(f"invalid {field_name}")


def _validate_submit_attempt_id(attempt_id: Any) -> None:
    if not isinstance(attempt_id, str):
        raise SubmitStateError("invalid submit attempt")
    try:
        parsed = uuid.UUID(attempt_id, version=4)
    except (AttributeError, TypeError, ValueError):
        raise SubmitStateError("invalid submit attempt")
    if parsed.version != 4 or str(parsed) != attempt_id:
        raise SubmitStateError("invalid submit attempt")


def _validate_submit_actor(actor: Any) -> None:
    if actor not in _SUBMIT_ACTORS:
        raise SubmitStateError("invalid submit attempt")


def _validate_submit_error_code(error_code: Any) -> None:
    if error_code is None:
        return
    if error_code not in _SUBMIT_ATTEMPT_ERROR_CODES:
        raise SubmitStateError("invalid submit attempt")


def append_submit_attempt(
    payload: dict[str, Any],
    attempt: dict[str, Any],
) -> dict[str, Any]:
    """Return a deep-copied payload with the attempt appended to submit_attempts.

    Does not mutate the input payload. Enforces exact allowed keys and
    validates all fields. Rejects unknown extra fields and raw/untrusted values.
    """
    if not isinstance(attempt, dict):
        raise SubmitStateError("attempt must be a dict")

    # Reject unknown extra fields
    extra_keys = set(attempt.keys()) - _SUBMIT_ATTEMPT_ALLOWED_KEYS
    if extra_keys:
        raise SubmitStateError("invalid submit attempt")

    # Reject missing required fields
    missing = _SUBMIT_ATTEMPT_REQUIRED_KEYS - set(attempt.keys())
    if missing:
        raise SubmitStateError("attempt missing required fields")

    # attempt_id: canonical UUID4 string
    _validate_submit_attempt_id(attempt.get("attempt_id"))

    # client_order_id: Alpaca-compatible
    _validate_client_order_id(attempt.get("client_order_id"))

    # status: allowed enum
    _status = attempt.get("status")
    if _status not in _SUBMIT_ATTEMPT_STATUSES:
        raise SubmitStateError("invalid submit attempt status")

    # created_at: ISO datetime
    _validate_iso_datetime(attempt.get("created_at"), "created_at")

    # actor: safe submit-state actor only
    _validate_submit_actor(attempt.get("actor"))

    # risk_revalidated: bool
    _risk = attempt.get("risk_revalidated")
    if not isinstance(_risk, bool):
        raise SubmitStateError("invalid risk_revalidated")

    # sync_revalidated: bool
    _sync = attempt.get("sync_revalidated")
    if not isinstance(_sync, bool):
        raise SubmitStateError("invalid sync_revalidated")

    # broker_order_id: None or non-empty string
    _boid = attempt.get("broker_order_id")
    if _boid is not None and (not isinstance(_boid, str) or not _boid):
        raise SubmitStateError("invalid broker_order_id")

    # error_code: None or explicit safe enum
    _validate_submit_error_code(attempt.get("error_code"))

    submit_attempts = payload.get("submit_attempts")
    if not isinstance(submit_attempts, list):
        raise SubmitStateError("submit_attempts must be a list")

    new_payload = copy.deepcopy(payload)
    new_payload["submit_attempts"] = list(new_payload["submit_attempts"])
    new_payload["submit_attempts"].append(copy.deepcopy(attempt))
    return new_payload


# ---------------------------------------------------------------------------
# Build submit-requested payload (pure function)
# ---------------------------------------------------------------------------

def build_submit_requested_payload(
    payload: dict[str, Any],
    *,
    order_id: str,
    client_order_id: str,
    now: datetime,
    actor: str = "submit:cli",
    attempt_id: str | None = None,
) -> dict[str, Any]:
    """Return a deep-copied payload transitioned to submit_requested state.

    Does not mutate the input payload. Validates all preconditions:
      - payload status must be "approved"
      - order_hash must match recomputed hash
      - client_order_id must be Alpaca-compatible
      - client_order_id must equal compute_client_order_id(order_id, order_hash)

    Sets:
      - status = "submit_requested"
      - client_order_id = client_order_id
      - submit_requested_at = now.isoformat()
      - submitted_at remains unchanged
      - appends status transition
      - appends submit_attempt entry
    """
    if payload.get("status") != "approved":
        raise SubmitStateError("payload status must be approved")

    if not verify_order_hash(payload):
        raise InvalidPendingOrderError("order hash mismatch")

    _validate_client_order_id(client_order_id)
    _validate_submit_actor(actor)

    expected_cid = compute_client_order_id(order_id, payload["order_hash"])
    if client_order_id != expected_cid:
        raise SubmitStateError("client_order_id does not match deterministic computation")

    existing_cid = payload.get("client_order_id")
    if existing_cid is not None:
        _validate_client_order_id(existing_cid)
        if existing_cid != expected_cid:
            raise SubmitStateError("client_order_id mismatch")
        if existing_cid != client_order_id:
            raise SubmitStateError("client_order_id mismatch")

    new_payload = copy.deepcopy(payload)
    new_payload["status"] = "submit_requested"
    new_payload["client_order_id"] = client_order_id
    new_payload["submit_requested_at"] = now.isoformat()
    # submitted_at must remain unchanged / null in Batch 4.6

    transition: dict[str, Any] = {
        "status": "submit_requested",
        "at": now.isoformat(),
        "actor": actor,
    }
    new_payload["status_transitions"] = list(new_payload.get("status_transitions", []))
    new_payload["status_transitions"].append(transition)

    safe_attempt_id = attempt_id or str(uuid.uuid4())
    attempt = {
        "attempt_id": safe_attempt_id,
        "client_order_id": client_order_id,
        "status": "submit_requested",
        "created_at": now.isoformat(),
        "actor": actor,
        "risk_revalidated": True,
        "sync_revalidated": True,
        "broker_order_id": None,
        "error_code": None,
    }
    return append_submit_attempt(new_payload, attempt)


# ---------------------------------------------------------------------------
# Atomic submit-requested mutation
# ---------------------------------------------------------------------------

def mark_submit_requested(
    path: Path,
    *,
    order_id: str,
    client_order_id: str,
    actor: str = "submit:cli",
    now: datetime | None = None,
    attempt_id: str | None = None,
) -> Path:
    """Atomically transition the pending order to submit_requested state.

    Preconditions (fail-closed):
      - File must exist and be valid v2 schema.
      - status must be "approved".
      - Hash must match.
      - client_order_id must be valid and match deterministic computation.
      - If payload already has a client_order_id, it must match the provided one.

    Side effects:
      - Sets payload["status"] = "submit_requested"
      - Sets payload["client_order_id"] = client_order_id
      - Sets payload["submit_requested_at"] = now.isoformat()
      - Appends status_transition entry
      - Appends submit_attempt entry with status="submit_requested"

    Returns the path to the updated file.
    """
    payload = load_pending_order(path)

    if payload.get("status") != "approved":
        raise SubmitStateError("status must be approved")

    expected_cid = compute_client_order_id(order_id, payload["order_hash"])
    existing_cid = payload.get("client_order_id")
    if existing_cid is not None and existing_cid != expected_cid:
        raise SubmitStateError("stored client_order_id does not match deterministic computation")

    if existing_cid is not None and existing_cid != client_order_id:
        raise SubmitStateError("provided client_order_id does not match stored value")

    if now is None:
        now = datetime.now(UTC)

    new_payload = build_submit_requested_payload(
        payload,
        order_id=order_id,
        client_order_id=client_order_id,
        now=now,
        actor=actor,
        attempt_id=attempt_id,
    )
    _atomic_write_json(path, new_payload)
    return path


# ---------------------------------------------------------------------------
# Broker status allowlist
# ---------------------------------------------------------------------------

_BROKER_STATUS_ALLOWLIST = frozenset({
    "new",
    "partially_filled",
    "filled",
    "done_for_day",
    "canceled",
    "expired",
    "replaced",
    "pending_cancel",
    "pending_replace",
    "accepted",
    "pending_new",
    "accepted_for_bidding",
    "stopped",
    "rejected",
    "suspended",
    "calculated",
    "open",
    "pending",
    "cancelled",
})


def _validate_broker_order_id(broker_order_id: Any) -> None:
    """Validate a broker_order_id. Raises SubmitStateError with static message.

    Rejects secret-shaped values to prevent accidental leakage.
    """
    if not isinstance(broker_order_id, str) or not broker_order_id:
        raise SubmitStateError("invalid broker_order_id")
    # Reject obvious secret-shaped values
    upper = broker_order_id.upper()
    if "API_KEY" in upper or "SECRET" in upper or "TOKEN" in upper or "PASSWORD" in upper:
        raise SubmitStateError("invalid broker_order_id")


def _validate_broker_status(broker_status: Any) -> None:
    """Validate a broker_status against the safe allowlist.

    Raises SubmitStateError with a static message (no raw value leak).
    """
    if not isinstance(broker_status, str) or broker_status not in _BROKER_STATUS_ALLOWLIST:
        raise SubmitStateError("invalid broker_status")


# ---------------------------------------------------------------------------
# Post-submit state mutation helpers (all use atomic write)
# ---------------------------------------------------------------------------

def _update_last_attempt_status(
    payload: dict[str, Any],
    status: str,
    error_code: str | None = None,
    broker_order_id: str | None = None,
) -> None:
    """Update the last submit_attempt entry in-place.

    Does not validate; callers must ensure status/error_code are safe.
    """
    attempts = payload.get("submit_attempts")
    if isinstance(attempts, list) and attempts:
        last = attempts[-1]
        last["status"] = status
        if error_code is not None:
            last["error_code"] = error_code
        if broker_order_id is not None:
            last["broker_order_id"] = broker_order_id


def mark_acknowledged(
    path: Path,
    *,
    broker_order_id: str,
    broker_status: str,
    now: datetime | None = None,
) -> Path:
    """Atomically update the pending order to acknowledged state.

    Preconditions (fail-closed):
      - File must exist and be valid v2 schema.
      - status must be "submit_requested".
      - broker_order_id must be a non-empty string.
      - broker_status must be in the safe allowlist.

    Side effects:
      - Sets payload["status"] = "acknowledged"
      - Sets payload["submitted_at"] = now.isoformat()
      - Sets payload["broker_order_id"] = broker_order_id
      - Sets payload["broker_status"] = broker_status
      - Updates the last submit_attempt entry:
          status="acknowledged", broker_order_id set, error_code stays None
      - Appends status_transition entry with static reason

    Returns the path to the updated file.
    """
    payload = load_pending_order(path)

    if payload.get("status") != "submit_requested":
        raise SubmitStateError("status must be submit_requested")

    _validate_broker_order_id(broker_order_id)
    _validate_broker_status(broker_status)

    if now is None:
        now = datetime.now(UTC)

    new_payload = copy.deepcopy(payload)
    new_payload["status"] = "acknowledged"
    new_payload["submitted_at"] = now.isoformat()
    new_payload["broker_order_id"] = broker_order_id
    new_payload["broker_status"] = broker_status

    _update_last_attempt_status(
        new_payload,
        status="acknowledged",
        broker_order_id=broker_order_id,
    )

    new_payload["status_transitions"] = list(new_payload.get("status_transitions", []))
    new_payload["status_transitions"].append({
        "status": "acknowledged",
        "at": now.isoformat(),
        "actor": "system",
        "reason": "broker_acknowledged",
    })

    _atomic_write_json(path, new_payload)
    return path


def mark_submit_failed(
    path: Path,
    *,
    error_code: str,
    now: datetime | None = None,
) -> Path:
    """Atomically mark the pending order as failed after broker rejection.

    Preconditions (fail-closed):
      - File must exist and be valid v2 schema.
      - status must be "submit_requested".
      - error_code must be in the safe allowlist.

    Side effects:
      - Sets payload["status"] = "failed"
      - Keeps submitted_at unchanged / null
      - Keeps broker_order_id unchanged / null
      - Updates the last submit_attempt entry: status="failed", error_code set
      - Appends status_transition entry

    Returns the path to the updated file.
    """
    payload = load_pending_order(path)

    if payload.get("status") != "submit_requested":
        raise SubmitStateError("status must be submit_requested")

    if error_code not in _SUBMIT_ATTEMPT_ERROR_CODES:
        raise SubmitStateError("invalid submit attempt")

    if now is None:
        now = datetime.now(UTC)

    new_payload = copy.deepcopy(payload)
    new_payload["status"] = "failed"

    _update_last_attempt_status(
        new_payload,
        status="failed",
        error_code=error_code,
    )

    new_payload["status_transitions"] = list(new_payload.get("status_transitions", []))
    new_payload["status_transitions"].append({
        "status": "failed",
        "at": now.isoformat(),
        "actor": "system",
        "reason": "broker_rejected",
        "code": error_code,
    })

    _atomic_write_json(path, new_payload)
    return path


def mark_submit_uncertain(
    path: Path,
    *,
    error_code: str,
    now: datetime | None = None,
) -> Path:
    """Atomically mark the pending order as uncertain after broker timeout/transport.

    Used ONLY for post-broker uncertainty (timeout, 5xx, transport, malformed
    response, client_order_id mismatch after request may have been sent, or
    local write failure after broker ACK).

    Preconditions (fail-closed):
      - File must exist and be valid v2 schema.
      - status must be "submit_requested".
      - error_code must be in the safe allowlist.

    Side effects:
      - Sets payload["status"] = "submit_uncertain"
      - Keeps submitted_at unchanged / null
      - Keeps broker_order_id unchanged / null
      - Updates the last submit_attempt entry: status="submit_uncertain", error_code set
      - Appends status_transition entry

    Returns the path to the updated file.
    """
    payload = load_pending_order(path)

    if payload.get("status") != "submit_requested":
        raise SubmitStateError("status must be submit_requested")

    if error_code not in _SUBMIT_ATTEMPT_ERROR_CODES:
        raise SubmitStateError("invalid submit attempt")

    if now is None:
        now = datetime.now(UTC)

    new_payload = copy.deepcopy(payload)
    new_payload["status"] = "submit_uncertain"

    _update_last_attempt_status(
        new_payload,
        status="submit_uncertain",
        error_code=error_code,
    )

    new_payload["status_transitions"] = list(new_payload.get("status_transitions", []))
    new_payload["status_transitions"].append({
        "status": "submit_uncertain",
        "at": now.isoformat(),
        "actor": "system",
        "reason": "broker_uncertain",
        "code": error_code,
    })

    _atomic_write_json(path, new_payload)
    return path


def mark_submit_prepare_failed(
    path: Path,
    *,
    error_code: str,
    now: datetime | None = None,
) -> Path:
    """Atomically mark the pending order as prepare-failed.

    Used ONLY for pre-broker local failure after submit_requested was written:
      - resolve_execution_broker returned None
      - execution broker object invalid
      - place_order callable missing

    Preconditions (fail-closed):
      - File must exist and be valid v2 schema.
      - status must be "submit_requested".
      - error_code must be exactly "execution_broker_unavailable" or
        "execution_broker_invalid".

    Side effects:
      - Sets payload["status"] = "submit_prepare_failed"
      - Keeps submitted_at unchanged / null
      - Keeps broker_order_id unchanged / null
      - Updates the last submit_attempt entry: status="submit_prepare_failed", error_code set
      - Appends status_transition entry

    Returns the path to the updated file.
    """
    payload = load_pending_order(path)

    if payload.get("status") != "submit_requested":
        raise SubmitStateError("status must be submit_requested")

    if error_code not in ("execution_broker_unavailable", "execution_broker_invalid"):
        raise SubmitStateError("invalid submit attempt")

    if now is None:
        now = datetime.now(UTC)

    new_payload = copy.deepcopy(payload)
    new_payload["status"] = "submit_prepare_failed"

    _update_last_attempt_status(
        new_payload,
        status="submit_prepare_failed",
        error_code=error_code,
    )

    new_payload["status_transitions"] = list(new_payload.get("status_transitions", []))
    new_payload["status_transitions"].append({
        "status": "submit_prepare_failed",
        "at": now.isoformat(),
        "actor": "system",
        "reason": "execution_broker_failed",
        "code": error_code,
    })

    _atomic_write_json(path, new_payload)
    return path
