# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    execution/approval.py
# PURPOSE: The human-in-the-loop gate for live orders. Parks an order on disk, and
#          later proves that the thing being approved is byte-for-byte the thing
#          that was proposed.
# DEPS:    hmac/hashlib (integrity), execution.order (the payload)
#
# DESIGN:  The pending-order file lives in a directory a human is invited to edit,
#          which makes it the softest surface in the order path. Three defences
#          layer over it:
#            1. order_hash  — detects any edit to the order fields;
#            2. HMAC        — detects an edit made by someone WITHOUT the secret,
#                             so a tamperer cannot simply recompute the hash;
#            3. TTL         — an approval that sat too long is void, so a stale
#                             file cannot be executed against a moved market.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from atlas_agent.execution.order import Order


# --- CONFIGURATIONS & CONSTANTS ---

def _get_approval_secret() -> str | None:
    """Read optional ATLAS_APPROVAL_SECRET_KEY from environment."""
    # Optional: without it the order_hash still catches accidental corruption, but not
    # a deliberate edit by someone who can just recompute the hash. The HMAC is what
    # upgrades this from tamper-EVIDENT to tamper-RESISTANT.
    return os.environ.get("ATLAS_APPROVAL_SECRET_KEY") or None


class InvalidApprovalIdError(ValueError):
    """Raised when a pending approval id cannot be safely mapped to a file."""


class InvalidPendingOrderError(ValueError):
    """Raised when a pending order file is malformed, tampered, or unsupported."""


# An order id becomes a FILENAME. Without this allowlist, an id like "../../etc/x"
# would let a caller write or read outside pending_orders/ — a path traversal on the
# one directory that decides which orders are allowed to execute.
_SAFE_APPROVAL_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


# ==============================================================================
# APPROVAL MANAGER
# ==============================================================================

class ApprovalManager:
    def __init__(
        self,
        pending_dir: str | Path = "pending_orders",
        *,
        secret_key: str | None = None,
    ) -> None:
        self.pending_dir = Path(pending_dir)
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self._secret_key = secret_key if secret_key is not None else _get_approval_secret()

    # --- Parking an order for review ---

    def create_pending_order(self, order: Order, *, ttl_minutes: int = 30) -> Path:
        # 30 minutes by default. An approval is consent to trade AT A PRICE, and that
        # consent decays: rubber-stamping an order and executing it hours later would
        # put it into a market the approver never saw.
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=ttl_minutes)
        order_dict = _order_to_dict(order)
        # Computed at creation and re-verified at approval. This is what makes "approve
        # order X" mean the X that was proposed, not an X someone edited in between.
        order_hash = _compute_order_hash(order_dict)
        transitions = [
            {"status": "pending_approval", "at": now.isoformat(), "actor": "system"}
        ]
        payload: dict[str, Any] = {
            "schema_version": "2",
            "order": order_dict,
            "approved": False,
            "created_at": now.isoformat(),
            "approved_at": None,
            "expires_at": expires_at.isoformat(),
            "approval_actor": None,
            "order_hash": order_hash,
            "status": "pending_approval",
            "status_transitions": transitions,
            "submit_attempts": [],
            "broker_order_id": None,
            "client_order_id": None,
            "fill_quantity": 0.0,
            "fill_price": None,
            "submitted_at": None,
        }
        payload["approval_hash_alg"] = "hmac-sha256" if self._secret_key else "sha256"
        payload["approval_hash"] = _compute_approval_hash(
            order_hash=order_hash,
            approved=False,
            approved_at=None,
            approval_actor=None,
            status="pending_approval",
            status_transitions=transitions,
            expires_at=expires_at.isoformat(),
            secret_key=self._secret_key,
        )
        path = self.path_for(order.id)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path

    # --- Recording an approval ---

    def approve(self, order_id: str, *, actor: str = "cli:user") -> Path:
        # _read_payload() validates and integrity-checks before we get here, so an order
        # that was edited on disk can never be approved — the tamper check runs BEFORE
        # the approval is granted, not after.
        path = self.path_for(order_id)
        if not path.exists():
            raise FileNotFoundError(f"pending order not found: {order_id}")
        payload = self._read_payload(path)
        # An anonymous approval is not an approval. `actor` ends up in the audit trail
        # as the answer to "who authorised this trade".
        if not isinstance(actor, str) or not actor.strip():
            raise InvalidPendingOrderError("approval actor invalid")
        expires_at_raw = payload.get("expires_at")
        if not expires_at_raw:
            raise InvalidPendingOrderError("missing expires_at")
        try:
            expires_at = datetime.fromisoformat(expires_at_raw)
        except (ValueError, TypeError):
            raise InvalidPendingOrderError("invalid expires_at")
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        # Expiry is checked at APPROVE time as well as at is_approved() time. Approving
        # an already-expired order would mint a fresh-looking approval over a stale
        # proposal — the TTL has to bind at every step, not just the last one.
        if datetime.now(UTC) > expires_at:
            raise InvalidPendingOrderError("pending order expired")
        now = datetime.now(UTC)
        payload["approved"] = True
        payload["approved_at"] = now.isoformat()
        payload["approval_actor"] = actor
        payload["status"] = "approved"
        payload["status_transitions"].append(
            {"status": "approved", "at": now.isoformat(), "actor": actor}
        )
        payload["approval_hash_alg"] = "hmac-sha256" if self._secret_key else "sha256"
        payload["approval_hash"] = _compute_approval_hash(
            order_hash=payload["order_hash"],
            approved=True,
            approved_at=now.isoformat(),
            approval_actor=actor,
            status="approved",
            status_transitions=payload["status_transitions"],
            expires_at=payload["expires_at"],
            secret_key=self._secret_key,
        )
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path

    # --- Checking an approval (the gate the router calls) ---

    def is_approved(self, order_id: str) -> bool:
        """Is this order approved, right now, and provably unmodified?

        Returns:
            True only if EVERY check passes. Every failure path returns False —
            never an exception, never a maybe. This is the predicate that stands
            between a proposal and a real trade, so the default answer is no.
        """
        path = self.path_for(order_id)
        if not path.exists():
            return False
        try:
            payload = self._read_payload(path)
            expires_at_raw = payload.get("expires_at")
            if not expires_at_raw:
                return False
            expires_at = datetime.fromisoformat(expires_at_raw)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            # Re-checked at submit time, not merely at approve time: an approval that has
            # expired while waiting in the queue is void, and this is the last chance to
            # notice before the order reaches the venue.
            if datetime.now(UTC) > expires_at:
                return False
            # `approved` and `status` must BOTH agree. They are two independent fields,
            # and a file where they disagree is a file that has been tampered with.
            if not payload.get("approved") or payload.get("status") != "approved":
                return False
            # "unknown" is explicitly rejected, not just falsy values: it is the
            # placeholder a v1→v2 upgrade leaves behind, and an upgraded record must not
            # count as a human decision nobody actually made.
            actor = payload.get("approval_actor")
            if not actor or actor == "unknown":
                return False
            approval_hash = payload.get("approval_hash")
            if not approval_hash or not isinstance(approval_hash, str):
                return False
            # Verify using the algorithm recorded in the payload so legacy orders
            # without approval_hash_alg still verify under plain SHA-256.
            alg = payload.get("approval_hash_alg", "sha256")
            secret_key = self._secret_key if alg == "hmac-sha256" else None
            recomputed = _compute_approval_hash(
                order_hash=payload.get("order_hash", ""),
                approved=payload.get("approved"),
                approved_at=payload.get("approved_at"),
                approval_actor=actor,
                status=payload.get("status", ""),
                status_transitions=payload.get("status_transitions", []),
                expires_at=payload.get("expires_at", ""),
                secret_key=secret_key,
            )
            # The tamper check. If a single approval field was edited on disk, the
            # recomputed hash will not match and the order is not approved.
            if approval_hash != recomputed:
                return False
            return True
        except (
            json.JSONDecodeError,
            InvalidPendingOrderError,
            KeyError,
            ValueError,
            TypeError,
            OSError,
        ):
            # A broad catch, and deliberately so: ANY failure to establish that this
            # order is approved means it is not approved. There is no error path here
            # that should propagate, because a caller that sees an exception might
            # handle it — and the only correct handling is "do not trade".
            return False

    # --- Reading and validating the file ---

    def _read_payload(self, path: Path) -> dict[str, Any]:
        raw = path.read_text(encoding="utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise InvalidPendingOrderError("invalid pending order file") from exc
        if not isinstance(payload, dict):
            raise InvalidPendingOrderError("pending order must be a JSON object")
        schema_version = payload.get("schema_version")
        if schema_version is None:
            if _has_v2_only_fields(payload):
                raise InvalidPendingOrderError("pending order schema invalid")
            payload = _upgrade_v1_to_v2(payload)
        elif schema_version == "1":
            payload = _upgrade_v1_to_v2(payload)
        elif schema_version != "2":
            raise InvalidPendingOrderError(
                "unsupported pending order schema version"
            )
        _validate_v2_payload_integrity(payload, secret_key=self._secret_key)
        return payload

    def path_for(self, order_id: str) -> Path:
        safe_id = _validate_approval_id(order_id)
        pending_dir = self.pending_dir.resolve()
        path = self.pending_dir / f"{safe_id}.json"
        resolved_path = path.resolve(strict=False)
        if resolved_path.parent != pending_dir:
            raise InvalidApprovalIdError("Invalid pending order id.")
        return path


# ==============================================================================
# INTEGRITY: HASHING & HMAC
# ==============================================================================

def _order_to_dict(order: Order) -> dict[str, object]:
    payload = asdict(order)
    # datetime is not JSON-serialisable, and the hash below is computed over JSON.
    # Normalising to ISO here keeps the hash reproducible across processes.
    payload["created_at"] = order.created_at.isoformat()
    return payload


def _compute_order_hash(order_dict: dict[str, Any]) -> str:
    """Compute sha256 of canonical JSON of the immutable order payload only."""
    # Covers ONLY the order fields — never the approval decision. The two are hashed
    # separately on purpose: approving an order changes the decision fields, and if
    # they shared one hash, every approval would invalidate the very hash that proves
    # the order was not edited.
    canonical = json.dumps(order_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _compute_approval_hash(
    order_hash: str,
    approved: bool,
    approved_at: str | None,
    approval_actor: str | None,
    status: str,
    status_transitions: list[dict[str, Any]],
    expires_at: str,
    secret_key: str | None = None,
) -> str:
    """Compute tamper-evident hash of approval decision fields.

    When secret_key is provided, uses HMAC-SHA256 for authentication.
    When absent, falls back to plain SHA256 for paper/demo compatibility.
    """
    # `order_hash` is folded INTO the approval hash, which binds the decision to one
    # specific order. Without that link, an attacker could lift a valid approval block
    # from one pending file and paste it over a different order.
    #
    # `expires_at` is included too, so the TTL cannot be extended by editing the file:
    # moving the expiry invalidates the hash.
    canonical = json.dumps(
        {
            "order_hash": order_hash,
            "approved": approved,
            "approved_at": approved_at,
            "approval_actor": approval_actor,
            "status": status,
            "status_transitions": status_transitions,
            "expires_at": expires_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    payload = canonical.encode("utf-8")
    # HMAC when a secret exists, plain SHA-256 when it does not. The difference is not
    # cosmetic: a plain hash is reproducible by anyone editing the file, so on its own
    # it detects only ACCIDENTAL corruption. Authentication of live approvals requires
    # the secret — which is why assert_live_hmac_approval() below insists on it.
    if secret_key:
        return hmac.new(secret_key.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hashlib.sha256(payload).hexdigest()


# ==============================================================================
# PAYLOAD VALIDATION
# ==============================================================================

# --- Numeric predicates ---

def _is_number(value: Any) -> bool:
    # `not isinstance(value, bool)` matters: in Python bool subclasses int, so True
    # would otherwise pass as a valid quantity and evaluate to 1.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_positive_finite(value: Any) -> bool:
    return _is_number(value) and math.isfinite(value) and value > 0


def _is_non_negative_finite(value: Any) -> bool:
    return _is_number(value) and math.isfinite(value) and value >= 0


def _require_iso_datetime(value: Any, message: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidPendingOrderError(message)
    try:
        datetime.fromisoformat(value)
    except ValueError:
        raise InvalidPendingOrderError(message)


def _require_optional_iso_datetime(value: Any, message: str) -> None:
    if value is None:
        return
    _require_iso_datetime(value, message)


def _require_optional_non_empty_string(value: Any, message: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise InvalidPendingOrderError(message)


def _has_v2_only_fields(payload: dict[str, Any]) -> bool:
    v2_only_fields = {
        "approval_actor",
        "order_hash",
        "status",
        "status_transitions",
        "submit_attempts",
        "broker_order_id",
        "client_order_id",
        "fill_quantity",
        "fill_price",
        "submitted_at",
    }
    return any(field in payload for field in v2_only_fields)


def _validate_order_payload(order_dict: dict[str, Any]) -> None:
    """Validate that an order dict represents a valid Order.

    Raises InvalidPendingOrderError with a static message on any validation failure.
    """
    required = {"symbol", "side", "quantity"}
    if not required.issubset(order_dict.keys()):
        raise InvalidPendingOrderError("order payload missing required fields")

    symbol = order_dict.get("symbol")
    if not isinstance(symbol, str) or not symbol.strip():
        raise InvalidPendingOrderError("order symbol invalid")

    side = order_dict.get("side")
    if side not in {"buy", "sell"}:
        raise InvalidPendingOrderError("order side invalid")

    if not _is_positive_finite(order_dict.get("quantity")):
        raise InvalidPendingOrderError("order quantity invalid")

    order_type = order_dict.get("order_type")
    if order_type not in {"market", "limit"}:
        raise InvalidPendingOrderError("order type invalid")

    limit_price = order_dict.get("limit_price")
    if limit_price is not None and not _is_positive_finite(limit_price):
        raise InvalidPendingOrderError("order limit_price invalid")

    confidence = order_dict.get("confidence")
    if not _is_number(confidence) or not math.isfinite(confidence) or not (0 <= confidence <= 1):
        raise InvalidPendingOrderError("order confidence invalid")

    stop_loss = order_dict.get("stop_loss")
    if stop_loss is not None and not _is_positive_finite(stop_loss):
        raise InvalidPendingOrderError("order stop_loss invalid")

    if not _is_positive_finite(order_dict.get("leverage")):
        raise InvalidPendingOrderError("order leverage invalid")

    order_id = order_dict.get("id")
    if not isinstance(order_id, str) or not order_id.strip():
        raise InvalidPendingOrderError("order id invalid")

    _require_iso_datetime(order_dict.get("created_at"), "order created_at invalid")

    source = order_dict.get("source")
    if not isinstance(source, str) or not source.strip():
        raise InvalidPendingOrderError("order source invalid")


def _validate_status_transition(item: Any) -> None:
    if not isinstance(item, dict):
        raise InvalidPendingOrderError("status transition invalid")
    status = item.get("status")
    if not isinstance(status, str) or not status.strip():
        raise InvalidPendingOrderError("status transition invalid")
    _require_iso_datetime(item.get("at"), "status transition invalid")
    _require_optional_non_empty_string(item.get("actor"), "status transition invalid")
    for field in ("reason", "code"):
        if field in item and not isinstance(item[field], str):
            raise InvalidPendingOrderError("status transition invalid")


def _validate_v2_top_level_schema(payload: dict[str, Any]) -> None:
    required_fields = {
        "schema_version",
        "order",
        "approved",
        "created_at",
        "approved_at",
        "expires_at",
        "approval_actor",
        "order_hash",
        "status",
        "status_transitions",
        "submit_attempts",
        "broker_order_id",
        "client_order_id",
        "fill_quantity",
        "fill_price",
        "submitted_at",
    }
    if not required_fields.issubset(payload.keys()):
        raise InvalidPendingOrderError("pending order schema invalid")
    if payload.get("schema_version") != "2":
        raise InvalidPendingOrderError("pending order schema invalid")
    if not isinstance(payload.get("approved"), bool):
        raise InvalidPendingOrderError("pending order schema invalid")
    _require_iso_datetime(payload.get("created_at"), "pending order schema invalid")
    _require_optional_iso_datetime(payload.get("approved_at"), "pending order schema invalid")
    _require_iso_datetime(payload.get("expires_at"), "pending order schema invalid")
    _require_optional_non_empty_string(payload.get("approval_actor"), "pending order schema invalid")

    approval_hash = payload.get("approval_hash")
    if approval_hash is not None and (not isinstance(approval_hash, str) or not approval_hash.strip()):
        raise InvalidPendingOrderError("pending order schema invalid")

    order_hash = payload.get("order_hash")
    if not isinstance(order_hash, str) or not order_hash.strip():
        raise InvalidPendingOrderError("missing order_hash")
    status = payload.get("status")
    if not isinstance(status, str) or not status.strip():
        raise InvalidPendingOrderError("pending order schema invalid")

    status_transitions = payload.get("status_transitions")
    if not isinstance(status_transitions, list):
        raise InvalidPendingOrderError("pending order schema invalid")
    for item in status_transitions:
        _validate_status_transition(item)

    if not isinstance(payload.get("submit_attempts"), list):
        raise InvalidPendingOrderError("pending order schema invalid")
    _require_optional_non_empty_string(payload.get("broker_order_id"), "pending order schema invalid")
    _require_optional_non_empty_string(payload.get("client_order_id"), "pending order schema invalid")
    if not _is_non_negative_finite(payload.get("fill_quantity")):
        raise InvalidPendingOrderError("pending order schema invalid")
    fill_price = payload.get("fill_price")
    if fill_price is not None and not _is_positive_finite(fill_price):
        raise InvalidPendingOrderError("pending order schema invalid")
    _require_optional_iso_datetime(payload.get("submitted_at"), "pending order schema invalid")


def _validate_v2_payload_integrity(
    payload: dict[str, Any],
    secret_key: str | None = None,
) -> None:
    """Validate that a v2 pending order's order_hash matches its order payload
    and that the order payload is structurally valid.

    For approved orders, also validates the approval_hash to detect tampering
    with approval decision fields. When secret_key is provided, HMAC-SHA256
    hashes are verified; when absent, plain SHA256 hashes are verified.
    If the payload uses HMAC but no secret_key is given, the approval hash
    presence is checked but the cryptographic verification is deferred to
    the caller that holds the secret.

    Raises InvalidPendingOrderError on any mismatch or missing required field.
    """
    _validate_v2_top_level_schema(payload)
    order = payload.get("order")
    if not order or not isinstance(order, dict):
        raise InvalidPendingOrderError("missing order payload")
    stored_hash = payload.get("order_hash")
    if not stored_hash or not isinstance(stored_hash, str):
        raise InvalidPendingOrderError("missing order_hash")
    recomputed = _compute_order_hash(order)
    if stored_hash != recomputed:
        raise InvalidPendingOrderError("order hash mismatch")
    _validate_order_payload(order)

    # Approval decision integrity: required for approved orders
    approved = payload.get("approved")
    status = payload.get("status")
    if approved and status == "approved":
        approval_hash = payload.get("approval_hash")
        if not approval_hash or not isinstance(approval_hash, str):
            raise InvalidPendingOrderError("missing approval_hash for approved order")
        actor = payload.get("approval_actor")
        if not actor or actor == "unknown":
            raise InvalidPendingOrderError("invalid approval_actor for approved order")
        alg = payload.get("approval_hash_alg", "sha256")
        # If HMAC is used and no secret is provided, skip cryptographic verification
        # but still validate schema and actor presence above.
        if alg == "hmac-sha256" and secret_key is None:
            pass
        else:
            recomputed_approval = _compute_approval_hash(
                order_hash=stored_hash,
                approved=approved,
                approved_at=payload.get("approved_at"),
                approval_actor=actor,
                status=status,
                status_transitions=payload.get("status_transitions", []),
                expires_at=payload.get("expires_at", ""),
                secret_key=secret_key if alg == "hmac-sha256" else None,
            )
            if approval_hash != recomputed_approval:
                raise InvalidPendingOrderError("approval hash mismatch")


def _upgrade_v1_to_v2(payload: dict[str, Any]) -> dict[str, Any]:
    """Safely upgrade a v1 pending order payload to v2.

    Preserves existing created_at and expires_at when present.
    Missing expires_at is preserved as None (callers should fail closed).

    v1 approved orders are NOT automatically trusted; approval is stripped
    and the order reverts to pending_approval so it must be re-approved
    through the proper v2 approval flow with integrity.
    """
    order_dict = payload.get("order")
    if not isinstance(order_dict, dict):
        raise InvalidPendingOrderError("missing order payload")
    order_hash = _compute_order_hash(order_dict)
    created_at = payload.get("created_at")
    approved = payload.get("approved", False)
    approved_at = payload.get("approved_at")
    expires_at = payload.get("expires_at")

    # Fail closed: strip v1 approval. v1 approved orders must be re-approved.
    if approved:
        approved = False
        approved_at = None

    status = "pending_approval"
    approval_actor = None
    transitions: list[dict[str, Any]] = []
    if created_at:
        transitions.append(
            {"status": "pending_approval", "at": created_at, "actor": "system"}
        )

    result: dict[str, Any] = {
        "schema_version": "2",
        "order": order_dict,
        "approved": approved,
        "created_at": created_at,
        "approved_at": approved_at,
        "expires_at": expires_at,
        "approval_actor": approval_actor,
        "order_hash": order_hash,
        "status": status,
        "status_transitions": transitions,
        "submit_attempts": [],
        "broker_order_id": None,
        "client_order_id": None,
        "fill_quantity": 0.0,
        "fill_price": None,
        "submitted_at": None,
    }

    result["approval_hash"] = _compute_approval_hash(
        order_hash=order_hash,
        approved=approved,
        approved_at=approved_at,
        approval_actor=approval_actor,
        status=status,
        status_transitions=transitions,
        expires_at=expires_at or "",
    )

    return result


# ==============================================================================
# LIVE-SUBMIT AUTHENTICATION GATE
# ==============================================================================

def assert_live_hmac_approval(payload: dict[str, Any]) -> None:
    """Fail closed if a live submit lacks HMAC-backed approval.

    When ATLAS_APPROVAL_SECRET_KEY is configured, live submit requires
    approval_hash_alg == 'hmac-sha256'. When the secret is not configured,
    legacy SHA-256 approvals are still accepted to preserve backward
    compatibility for existing deployments and reviewer/demo workflows.
    """
    # A DOWNGRADE guard, not an authentication check. Once a secret is configured,
    # an approval that carries only a plain SHA-256 hash is refused — otherwise an
    # attacker could strip the HMAC, recompute the weaker hash (which needs no secret),
    # and have it accepted as though nothing had changed.
    #
    # Note the deliberate limit of this guard: with no secret configured it returns
    # early and plain-SHA approvals are accepted. That is a backwards-compatibility
    # decision, and it means the HMAC layer protects only deployments that opted in.
    if _get_approval_secret() is None:
        return
    alg = payload.get("approval_hash_alg")
    if alg != "hmac-sha256":
        raise InvalidPendingOrderError(
            "Live submit requires HMAC-backed approval. "
            "Set ATLAS_APPROVAL_SECRET_KEY and re-approve the order."
        )


# ==============================================================================
# PATH SAFETY
# ==============================================================================

def _validate_approval_id(order_id: str) -> str:
    # The id becomes a path segment, so this is a path-traversal guard on the directory
    # that authorises live orders. "." and ".." are rejected before the regex because
    # they match no character class but are still dangerous as path components.
    if not isinstance(order_id, str):
        raise InvalidApprovalIdError("Invalid pending order id.")
    candidate = order_id.strip()
    if not candidate:
        raise InvalidApprovalIdError("Invalid pending order id.")
    if candidate in {".", ".."}:
        raise InvalidApprovalIdError("Invalid pending order id.")
    if not _SAFE_APPROVAL_ID.fullmatch(candidate):
        raise InvalidApprovalIdError("Invalid pending order id.")
    if any(part in {"", ".", ".."} for part in Path(candidate).parts):
        raise InvalidApprovalIdError("Invalid pending order id.")
    return candidate
