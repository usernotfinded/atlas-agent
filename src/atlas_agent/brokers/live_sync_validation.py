from __future__ import annotations

from typing import Any

from atlas_agent.brokers.models import BrokerSyncResult
from atlas_agent.brokers.resolver import BrokerStatus


def validate_live_sync(
    sync_result: BrokerSyncResult,
    broker_status: BrokerStatus,
) -> tuple[list[dict[str, str]], dict[str, Any] | None]:
    """Validate live broker sync result.

    Returns (sync_warnings, None) on success.
    Returns ([], error_result) on failure.

    Critical operations (account, positions, open_orders) fail closed.
    Noncritical operations (e.g., balances) are surfaced as structured warnings.
    Malformed broker_errors fail closed.
    """
    broker_errors = sync_result.diagnostics.get("broker_errors", [])

    # Malformed guard: must be a list of dicts with required string fields
    if not isinstance(broker_errors, list):
        return [], {
            "status": "error",
            "errors": ["live broker sync failed: malformed diagnostics"],
            "diagnostics": {
                "broker_status": broker_status.to_dict(),
                "sync_status": sync_result.status,
                "failed_operations": ["malformed_broker_errors"],
            },
        }

    required_fields = {"code", "operation", "broker", "message"}
    for entry in broker_errors:
        if not isinstance(entry, dict):
            return [], {
                "status": "error",
                "errors": ["live broker sync failed: malformed diagnostics"],
                "diagnostics": {
                    "broker_status": broker_status.to_dict(),
                    "sync_status": sync_result.status,
                    "failed_operations": ["malformed_broker_errors"],
                },
            }
        missing_fields = required_fields - set(entry.keys())
        if missing_fields:
            return [], {
                "status": "error",
                "errors": ["live broker sync failed: malformed diagnostics"],
                "diagnostics": {
                    "broker_status": broker_status.to_dict(),
                    "sync_status": sync_result.status,
                    "failed_operations": ["malformed_broker_errors"],
                },
            }
        if not all(isinstance(entry.get(f), str) for f in required_fields):
            return [], {
                "status": "error",
                "errors": ["live broker sync failed: malformed diagnostics"],
                "diagnostics": {
                    "broker_status": broker_status.to_dict(),
                    "sync_status": sync_result.status,
                    "failed_operations": ["malformed_broker_errors"],
                },
            }

    failed_ops = {e.get("operation") for e in broker_errors}

    if sync_result.account is None:
        failed_ops.add("sync_account_state")

    critical_ops = {"sync_account_state", "sync_positions", "sync_open_orders"}
    if failed_ops & critical_ops:
        missing = sorted(failed_ops & critical_ops)
        return [], {
            "status": "error",
            "errors": [f"live broker sync failed: {', '.join(missing)}"],
            "diagnostics": {
                "broker_status": broker_status.to_dict(),
                "sync_status": sync_result.status,
                "failed_operations": missing,
            },
        }

    # Collect noncritical warnings
    sync_warnings: list[dict[str, str]] = []
    noncritical_ops = sorted(failed_ops - critical_ops)
    for op in noncritical_ops:
        entry = next((e for e in broker_errors if e.get("operation") == op), {})
        sync_warnings.append({
            "operation": op,
            "code": entry.get("code", "unknown"),
            "broker": entry.get("broker", "unknown"),
        })

    return sync_warnings, None
