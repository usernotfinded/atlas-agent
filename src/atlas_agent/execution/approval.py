from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from atlas_agent.execution.order import Order


class InvalidApprovalIdError(ValueError):
    """Raised when a pending approval id cannot be safely mapped to a file."""


class InvalidPendingOrderError(ValueError):
    """Raised when a pending order file is malformed, tampered, or unsupported."""


_SAFE_APPROVAL_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


class ApprovalManager:
    def __init__(self, pending_dir: str | Path = "pending_orders") -> None:
        self.pending_dir = Path(pending_dir)
        self.pending_dir.mkdir(parents=True, exist_ok=True)

    def create_pending_order(self, order: Order, *, ttl_minutes: int = 30) -> Path:
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=ttl_minutes)
        order_dict = _order_to_dict(order)
        order_hash = _compute_order_hash(order_dict)
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
            "status_transitions": [
                {"status": "pending_approval", "at": now.isoformat(), "actor": "system"}
            ],
            "submit_attempts": [],
            "broker_order_id": None,
            "client_order_id": None,
            "fill_quantity": 0.0,
            "fill_price": None,
            "submitted_at": None,
        }
        path = self.path_for(order.id)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def approve(self, order_id: str, *, actor: str = "cli:user") -> Path:
        path = self.path_for(order_id)
        if not path.exists():
            raise FileNotFoundError(f"pending order not found: {order_id}")
        payload = self._read_payload(path)
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
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def is_approved(self, order_id: str) -> bool:
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
            if datetime.now(UTC) > expires_at:
                return False
            return bool(payload.get("approved")) and payload.get("status") == "approved"
        except (
            json.JSONDecodeError,
            InvalidPendingOrderError,
            KeyError,
            ValueError,
            TypeError,
            OSError,
        ):
            return False

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
        _validate_v2_payload_integrity(payload)
        return payload

    def path_for(self, order_id: str) -> Path:
        safe_id = _validate_approval_id(order_id)
        pending_dir = self.pending_dir.resolve()
        path = self.pending_dir / f"{safe_id}.json"
        resolved_path = path.resolve(strict=False)
        if resolved_path.parent != pending_dir:
            raise InvalidApprovalIdError("Invalid pending order id.")
        return path


def _order_to_dict(order: Order) -> dict[str, object]:
    payload = asdict(order)
    payload["created_at"] = order.created_at.isoformat()
    return payload


def _compute_order_hash(order_dict: dict[str, Any]) -> str:
    """Compute sha256 of canonical JSON of the immutable order payload only."""
    canonical = json.dumps(order_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_number(value: Any) -> bool:
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


def _validate_v2_payload_integrity(payload: dict[str, Any]) -> None:
    """Validate that a v2 pending order's order_hash matches its order payload
    and that the order payload is structurally valid.

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


def _upgrade_v1_to_v2(payload: dict[str, Any]) -> dict[str, Any]:
    """Safely upgrade a v1 pending order payload to v2.

    Preserves existing created_at and expires_at when present.
    Missing expires_at is preserved as None (callers should fail closed).
    """
    order_dict = payload.get("order")
    if not isinstance(order_dict, dict):
        raise InvalidPendingOrderError("missing order payload")
    order_hash = _compute_order_hash(order_dict)
    created_at = payload.get("created_at")
    approved = payload.get("approved", False)
    approved_at = payload.get("approved_at")
    expires_at = payload.get("expires_at")
    status = "approved" if approved else "pending_approval"
    transitions: list[dict[str, Any]] = []
    if created_at:
        transitions.append(
            {"status": "pending_approval", "at": created_at, "actor": "system"}
        )
    if approved and approved_at:
        transitions.append(
            {"status": "approved", "at": approved_at, "actor": "unknown"}
        )
    return {
        "schema_version": "2",
        "order": order_dict,
        "approved": approved,
        "created_at": created_at,
        "approved_at": approved_at,
        "expires_at": expires_at,
        "approval_actor": "unknown" if approved else None,
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


def _validate_approval_id(order_id: str) -> str:
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
