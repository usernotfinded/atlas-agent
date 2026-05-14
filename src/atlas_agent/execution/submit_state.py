from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atlas_agent.execution.approval import (
    InvalidPendingOrderError,
    _compute_order_hash,
    _validate_v2_payload_integrity,
)


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
