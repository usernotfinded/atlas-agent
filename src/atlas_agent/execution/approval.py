from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from atlas_agent.execution.order import Order


class InvalidApprovalIdError(ValueError):
    """Raised when a pending approval id cannot be safely mapped to a file."""


_SAFE_APPROVAL_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


class ApprovalManager:
    def __init__(self, pending_dir: str | Path = "pending_orders") -> None:
        self.pending_dir = Path(pending_dir)
        self.pending_dir.mkdir(parents=True, exist_ok=True)

    def create_pending_order(self, order: Order, *, ttl_minutes: int = 30) -> Path:
        expires_at = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
        payload = {
            "order": _order_to_dict(order),
            "approved": False,
            "created_at": datetime.now(UTC).isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        path = self.path_for(order.id)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def approve(self, order_id: str) -> Path:
        path = self.path_for(order_id)
        if not path.exists():
            raise FileNotFoundError(f"pending order not found: {order_id}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["approved"] = True
        payload["approved_at"] = datetime.now(UTC).isoformat()
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def is_approved(self, order_id: str) -> bool:
        path = self.path_for(order_id)
        if not path.exists():
            return False
        payload = json.loads(path.read_text(encoding="utf-8"))
        expires_at = datetime.fromisoformat(payload["expires_at"])
        if datetime.now(UTC) > expires_at:
            return False
        return bool(payload.get("approved"))

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
