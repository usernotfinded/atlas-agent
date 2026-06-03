"""Provider readiness gate and capability inventory.

This module provides a local-only capability inventory and policy gate
for evaluating whether a provider request should be allowed.

It is strictly dry-run, audit-only, policy-only. It does NOT:
  - Make network calls
  - Read API keys
  - Call providers
  - Touch broker adapters
  - Enable live trading
  - Authorize any execution
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atlas_agent.providers.provider_preflight import (
    validate_max_context_chars,
    validate_model_id,
    validate_provider_id,
    validate_purpose,
)


def _utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def generate_capability_inventory() -> dict[str, Any]:
    """Generate a local capability inventory for providers.

    Inspects local provider modules without importing SDKs or running execution.
    Does not read API key values.
    """
    providers_dir = Path(__file__).parent
    known_providers: list[str] = []

    if providers_dir.exists():
        for f in providers_dir.glob("*.py"):
            name = f.stem
            if name not in (
                "__init__",
                "base",
                "factory",
                "provider_preflight",
                "provider_readiness",
                "adapters",
                "catalog",
                "runtime",
            ):
                known_providers.append(name)

    if not known_providers:
        known_providers = [
            "openrouter",
            "anthropic",
            "openai_compatible",
            "local_command",
            "null_provider",
        ]

    providers_data = []
    for pid in sorted(known_providers):
        providers_data.append(
            {
                "provider_id": pid,
                "adapter_module_present": True,
                "execution_enabled_by_default": False,
                "network_required_for_execution": pid
                not in ("local_command", "null_provider"),
                "credentials_required_for_execution": pid
                not in ("local_command", "null_provider"),
                "credentials_loaded": False,
                "network_used": False,
                "provider_call_made": False,
                "supported_current_modes": [
                    "preflight",
                    "validate-preflight",
                    "bundle-preflight",
                    "verify-preflight-bundle",
                    "smoke-preflight-chain",
                ],
                "blocked_current_modes": [
                    "real-provider-call",
                    "broker-action",
                    "trade-approval",
                ],
            }
        )

    return {
        "artifact_type": "provider_capability_inventory",
        "schema_version": 1,
        "generated_at": _utc_timestamp(),
        "providers": providers_data,
        "global_safety_summary": {
            "provider_execution_enabled": False,
            "network_used": False,
            "credentials_loaded": False,
            "broker_touched": False,
            "live_trading_enabled": False,
            "pending_order_created": False,
            "order_approved": False,
        },
    }


def evaluate_provider_readiness(
    provider_id: str,
    model_id: str,
    purpose: str,
    max_context_chars: int,
) -> dict[str, Any]:
    """Evaluate a hypothetical provider request against the safety policy.

    Returns a readiness report. Decision is always preflight_only.
    """
    valid_provider = validate_provider_id(provider_id)
    valid_model = validate_model_id(model_id)
    valid_purpose = validate_purpose(purpose)
    valid_context = validate_max_context_chars(max_context_chars)

    return {
        "artifact_type": "provider_readiness_report",
        "schema_version": 1,
        "valid": True,
        "provider_id": valid_provider,
        "model_id": valid_model,
        "purpose": valid_purpose,
        "max_context_chars": valid_context,
        "decision": "preflight_only",
        "provider_execution_allowed": False,
        "network_allowed": False,
        "credentials_allowed": False,
        "broker_allowed": False,
        "live_trading_allowed": False,
        "manual_review_required": True,
        "required_evidence": [
            "provider_call_plan",
            "provider_preflight_validation_report",
            "provider_preflight_evidence_bundle_manifest",
            "provider_preflight_smoke_report",
        ],
        "blockers": [
            "Provider execution is disabled by policy.",
            "Network calls are disabled for this gate.",
            "Credentials are not loaded by this gate.",
            "Broker and live trading paths are out of scope.",
        ],
        "allowed_actions": [
            "generate_preflight_artifact",
            "validate_preflight_artifact",
            "bundle_preflight_evidence",
            "verify_preflight_bundle",
            "run_preflight_smoke_chain",
        ],
        "forbidden_actions": [
            "send_provider_request",
            "load_api_key",
            "touch_broker",
            "create_order",
            "approve_order",
        ],
        "safety_summary": {
            "provider_call_made": False,
            "network_used": False,
            "credentials_loaded": False,
            "broker_touched": False,
            "live_trading_enabled": False,
            "pending_order_created": False,
            "order_approved": False,
        },
    }
