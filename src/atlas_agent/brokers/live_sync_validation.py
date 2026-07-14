# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    brokers/live_sync_validation.py
# PURPOSE: Decides whether we know enough about the account to trade it. A live
#          submit is only safe if our picture of the venue is complete — sizing an
#          order against a half-synced portfolio is how limits get breached.
# DEPS:    brokers.models (sync result), brokers.resolver (broker status)
#
# DESIGN:  Two tiers. Critical facts (account, positions, open orders) fail CLOSED:
#          without them we cannot compute exposure, so we must not trade. Everything
#          else degrades to a warning.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from typing import Any

from atlas_agent.brokers.models import BrokerSyncResult
from atlas_agent.brokers.resolver import BrokerStatus


# ==============================================================================
# LIVE SYNC VALIDATION
# ==============================================================================

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

    # Malformed diagnostics fail CLOSED. This looks like paranoia about a log field,
    # but it is not: the shape of `broker_errors` is what the critical-op check below
    # is computed from. If we cannot parse it, we cannot know whether a critical sync
    # failed — and "I don't know" must never resolve to "go ahead and trade live".
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

    # A missing account counts as a failure even when the broker reported no error.
    # A sync that "succeeded" with no account state is still a sync we cannot size an
    # order from, and trusting the absence of an error over the absence of data is
    # exactly the kind of gap that lets a bad submit through.
    if sync_result.account is None:
        failed_ops.add("sync_account_state")

    # These three are what exposure is computed from — equity, what we hold, and what
    # is already working. Missing any one of them makes every risk limit unenforceable,
    # so the answer is no, not "proceed with a warning".
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

    # Everything else (balances, for instance) is informational: nice to have, but not
    # something exposure depends on. Blocking a live submit because a balances endpoint
    # timed out would make the system brittle without making it safer.
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
