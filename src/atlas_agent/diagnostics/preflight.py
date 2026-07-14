# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    diagnostics/preflight.py
# PURPOSE: Answers "is this install actually capable of running?" — dependencies,
#          workspace layout, config — BEFORE anything is attempted. Read-only.
# DEPS:    importlib.util (dependency probing without importing)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

from atlas_agent.brokers.status import get_broker_support_entry
from atlas_agent.config.schema import AtlasConfig
from atlas_agent.providers.catalog import get_provider_profile, normalize_provider_id


REDACTED = "[REDACTED]"
_PLACEHOLDER_VALUES = {
    "changeme",
    "placeholder",
    "replace-me",
    "replace_me",
    "your-api-key",
    "your_api_key",
}

_BROKER_CREDENTIALS: dict[str, tuple[tuple[str, ...], ...]] = {
    "alpaca": (
        ("ALPACA_API_KEY",),
        ("ALPACA_SECRET_KEY",),
    ),
    "binance": (
        ("BINANCE_API_KEY",),
        ("BINANCE_API_SECRET", "BINANCE_SECRET_KEY"),
    ),
    "ccxt": (
        ("CCXT_API_KEY", "EXCHANGE_API_KEY"),
    ),
}

_BROKER_OPTIONAL_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "binance": ("ccxt",),
    "ccxt": ("ccxt",),
}


def _secret_format_category(value: str | None) -> str:
    if not value:
        return "absent"
    normalized = value.strip().lower()
    if normalized in _PLACEHOLDER_VALUES or normalized.startswith(
        ("your_", "your-", "replace_", "replace-", "<")
    ):
        return "placeholder"
    return "present_nonempty"


def _credential_check(env_vars: tuple[str, ...]) -> dict[str, Any]:
    matched_env_var = ""
    value: str | None = None
    for env_var in env_vars:
        candidate = os.getenv(env_var)
        if candidate:
            matched_env_var = env_var
            value = candidate
            break
    present = value is not None
    return {
        "env_vars": list(env_vars),
        "matched_env_var": matched_env_var or None,
        "secret_state": "present_redacted" if present else "absent",
        "format_category": _secret_format_category(value),
        "redacted_value": REDACTED if present else None,
    }


def _dependency_state(modules: tuple[str, ...]) -> dict[str, Any]:
    if not modules:
        return {
            "status": "not_required",
            "modules": [],
            "missing": [],
        }

    missing: list[str] = []
    for module in modules:
        try:
            available = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            available = False
        if not available:
            missing.append(module)
    return {
        "status": "missing_optional_dependency" if missing else "available",
        "modules": list(modules),
        "missing": missing,
    }


def _provider_base_url_configured(config: AtlasConfig, provider_id: str) -> bool:
    if (config.model.base_url or "").strip():
        return True
    provider_config = getattr(
        config.providers,
        provider_id.replace("-", "_"),
        None,
    )
    return bool(
        provider_config is not None
        and (getattr(provider_config, "base_url", "") or "").strip()
    )


def _is_local_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _google_oauth_credential_checks() -> list[dict[str, Any]]:
    token_check = _credential_check(
        ("ATLAS_GOOGLE_OAUTH_ACCESS_TOKEN", "GOOGLE_OAUTH_ACCESS_TOKEN")
    )
    adc_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    adc_present = bool(adc_path and _is_local_file(Path(adc_path).expanduser()))
    default_adc_present = _is_local_file(
        Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    )
    return [
        token_check,
        {
            "env_vars": ["GOOGLE_APPLICATION_CREDENTIALS"],
            "matched_env_var": "GOOGLE_APPLICATION_CREDENTIALS" if adc_present else None,
            "secret_state": "present_redacted" if adc_present else "absent",
            "format_category": "local_file_reference" if adc_present else "absent",
            "redacted_value": REDACTED if adc_present else None,
        },
        {
            "env_vars": ["gcloud_application_default_credentials"],
            "matched_env_var": (
                "gcloud_application_default_credentials"
                if default_adc_present
                else None
            ),
            "secret_state": (
                "present_redacted" if default_adc_present else "absent"
            ),
            "format_category": "local_file" if default_adc_present else "absent",
            "redacted_value": REDACTED if default_adc_present else None,
        },
    ]


def diagnose_provider(config: AtlasConfig) -> dict[str, Any]:
    requested_provider = (config.model.provider or "").strip()
    provider_id = normalize_provider_id(requested_provider)
    profile = get_provider_profile(provider_id)

    if profile is None:
        return {
            "provider_id": provider_id,
            "model": (config.model.model or "").strip(),
            "status": "unsupported_provider",
            "configured": False,
            "credential_checks": [],
            "optional_dependency": _dependency_state(()),
            "network_check": "skipped",
            "execution_enabled": False,
            "readiness_hint": "Choose a provider from `atlas model providers`.",
        }

    auth_method = "api_key"
    if provider_id == "google":
        auth_method = (
            getattr(config.model.google, "auth_method", None) or "api_key"
        ).strip()

    if provider_id == "google" and auth_method == "oauth_adc":
        credential_checks = _google_oauth_credential_checks()
        credentials_required = True
    else:
        credential_checks = [
            _credential_check((env_var,))
            for env_var in profile.env_precedence
        ]
        credentials_required = profile.key_required

    credentials_ready = any(
        item["secret_state"] == "present_redacted"
        and item["format_category"] != "placeholder"
        for item in credential_checks
    )
    model_configured = bool((config.model.model or "").strip())
    base_url_configured = (
        not profile.base_url_required
        or bool(profile.base_url)
        or _provider_base_url_configured(config, provider_id)
    )

    if profile.status in {"legacy", "internal"}:
        status = "disabled_by_safety_policy"
        hint = "Select a user-facing provider for agentic workflows."
    elif credentials_required and not credentials_ready:
        status = "missing_credentials"
        hint = "Configure the required credential locally; no connection was attempted."
    elif profile.model_required and not model_configured:
        status = "configuration_incomplete"
        hint = "Configure a model ID; no connection was attempted."
    elif not base_url_configured:
        status = "configuration_incomplete"
        hint = "Configure the provider base URL; no connection was attempted."
    else:
        status = "configured"
        hint = "Local configuration is present. Connectivity was not tested."

    return {
        "provider_id": profile.id,
        "provider_label": profile.display_name,
        "model": (config.model.model or "").strip(),
        "status": status,
        "configured": status == "configured",
        "auth_method": auth_method,
        "credential_requirement": (
            "required" if credentials_required else "optional_or_not_required"
        ),
        "credential_checks": credential_checks,
        "optional_dependency": _dependency_state(()),
        "network_check": "skipped",
        "execution_enabled": False,
        "readiness_hint": hint,
    }


def diagnose_broker(config: AtlasConfig) -> dict[str, Any]:
    requested_broker = (config.broker.provider or "none").strip().lower()
    broker_id = "ibkr" if requested_broker == "ibkr_stub" else requested_broker
    support = get_broker_support_entry(broker_id)
    credential_checks = [
        _credential_check(env_vars)
        for env_vars in _BROKER_CREDENTIALS.get(broker_id, ())
    ]
    credentials_ready = all(
        item["secret_state"] == "present_redacted"
        and item["format_category"] != "placeholder"
        for item in credential_checks
    )
    dependency = _dependency_state(
        _BROKER_OPTIONAL_DEPENDENCIES.get(broker_id, ())
    )

    if broker_id in {"", "none", "paper"}:
        status = "paper_only_available"
        hint = "PaperBroker is the safe default; no live broker is configured."
    elif support is None:
        status = "unsupported_broker"
        hint = "The configured broker is not in the static support inventory."
    elif support.status in {"disabled", "placeholder"}:
        status = "disabled_by_safety_policy"
        hint = "This adapter is disabled or a placeholder and cannot execute."
    elif credential_checks and not credentials_ready:
        status = "missing_credentials"
        hint = "Configure the required credentials locally; no connection was attempted."
    elif dependency["status"] == "missing_optional_dependency":
        status = "missing_optional_dependency"
        hint = "Install the optional local dependency before further configuration."
    elif not config.broker.enable_live_trading or not config.broker.enable_live_submit:
        status = "disabled_by_safety_policy"
        hint = "Live trading or live submit is disabled; paper mode remains available."
    else:
        status = "live_execution_blocked"
        hint = (
            "Local settings are present, but this diagnostic does not evaluate or "
            "authorize runtime live gates."
        )

    return {
        "broker_id": broker_id or "none",
        "status": status,
        "configured": support is not None and broker_id not in {"", "none", "paper"},
        "support": support.to_dict() if support is not None else None,
        "credential_checks": credential_checks,
        "optional_dependency": dependency,
        "configured_live_trading": bool(config.broker.enable_live_trading),
        "configured_live_submit": bool(config.broker.enable_live_submit),
        "live_execution_blocked": True,
        "paper_only_available": True,
        "network_check": "skipped",
        "client_instantiated": False,
        "readiness_hint": hint,
    }


def build_preflight_report(config: AtlasConfig) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "command": "atlas doctor",
        "diagnostic_mode": "read_only_local",
        "network_check": "skipped",
        "execution_enabled": False,
        "safe_default": "paper_only",
        "provider": diagnose_provider(config),
        "broker": diagnose_broker(config),
    }


def render_preflight_report(report: dict[str, Any]) -> str:
    provider = report["provider"]
    broker = report["broker"]
    lines = [
        "Atlas Doctor",
        "Safety: read-only local diagnostics; network and execution checks skipped.",
        "",
        "Provider",
        f"  provider: {provider['provider_id']}",
        f"  model: {provider.get('model') or '(not configured)'}",
        f"  status: {provider['status']}",
        "  network_check: skipped",
        "  execution_enabled: false",
    ]
    for check in provider["credential_checks"]:
        env_names = " | ".join(check["env_vars"])
        lines.append(
            f"  credential {env_names}: {check['secret_state']} "
            f"({check['format_category']})"
        )
        if check["redacted_value"]:
            lines.append(f"    value: {check['redacted_value']}")
    lines.extend(
        [
            f"  hint: {provider['readiness_hint']}",
            "",
            "Broker",
            f"  broker: {broker['broker_id']}",
            f"  status: {broker['status']}",
            f"  live_trading_configured: {str(broker['configured_live_trading']).lower()}",
            f"  live_submit_configured: {str(broker['configured_live_submit']).lower()}",
            "  live_execution_blocked: true",
            "  paper_only_available: true",
            "  network_check: skipped",
            "  client_instantiated: false",
        ]
    )
    for check in broker["credential_checks"]:
        env_names = " | ".join(check["env_vars"])
        lines.append(
            f"  credential {env_names}: {check['secret_state']} "
            f"({check['format_category']})"
        )
        if check["redacted_value"]:
            lines.append(f"    value: {check['redacted_value']}")
    dependency = broker["optional_dependency"]
    lines.append(f"  optional_dependency: {dependency['status']}")
    if dependency["missing"]:
        lines.append(f"    missing: {', '.join(dependency['missing'])}")
    lines.append(f"  hint: {broker['readiness_hint']}")
    return "\n".join(lines)
