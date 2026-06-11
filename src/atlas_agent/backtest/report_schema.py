"""Backtest report schema validator.

Provides a lightweight, dependency-free schema contract for backtest
JSON reports so that downstream tooling and reviewers can detect
silent structural drift.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

REPORT_SCHEMA_VERSION = "backtest.report.v1"

REQUIRED_TOP_LEVEL_KEYS = {
    "schema_version",
    "run_id",
    "status",
    "config",
    "metrics",
    "strategy_metadata",
    "fills",
    "equity_curve",
    "diagnostics",
    "generated_at",
    "disclaimer",
    "report_type",
}

REQUIRED_METRIC_KEYS = {
    "total_return_pct",
    "max_drawdown_pct",
    "trade_count",
    "final_equity",
    "initial_equity",
}

REQUIRED_CONFIG_KEYS = {
    "run_id",
    "symbol",
    "data_path",
    "initial_equity",
    "strategy_mode",
}

ALLOWED_STATUSES = {"completed", "failed", "blocked"}


class ReportSchemaError(ValueError):
    """Raised when a backtest report violates the schema contract."""


@dataclass(frozen=True)
class SchemaValidationResult:
    """Structured result from schema validation."""

    status: str
    valid: bool
    error: str | None = None
    errors: list[str] | None = None
    schema_version: str | None = None


def get_schema_validation_result(data: Any) -> SchemaValidationResult:
    """Return a structured schema validation result for a raw report dict.

    This is backward-compatible with ``get_schema_status()`` but provides
    machine-readable fields (``valid``, ``error``, ``schema_version``)
    for downstream consumers.
    """
    status = get_schema_status(data)
    version = data.get("schema_version") if isinstance(data, dict) else None
    if status == "valid":
        return SchemaValidationResult(status=status, valid=True, schema_version=version)
    if status == "legacy":
        return SchemaValidationResult(status=status, valid=False, schema_version=version)
    if status == "unreadable":
        return SchemaValidationResult(status=status, valid=False, error=status, schema_version=version)
    # invalid: collect all errors
    errors = collect_backtest_report_schema_errors(data) if isinstance(data, dict) else []
    first_error = errors[0] if errors else status
    return SchemaValidationResult(
        status=status,
        valid=False,
        error=first_error,
        errors=errors,
        schema_version=version,
    )


def collect_backtest_report_schema_errors(data: dict[str, Any]) -> list[str]:
    """Collect all schema validation errors from a report dict.

    Returns an empty list if the report is valid.
    """
    errors: list[str] = []

    if not isinstance(data, dict):
        errors.append("Report must be a JSON object (dict)")
        return errors

    missing_top = REQUIRED_TOP_LEVEL_KEYS - set(data.keys())
    if missing_top:
        errors.append(f"Missing top-level keys: {sorted(missing_top)}")

    if "schema_version" in data and data["schema_version"] != REPORT_SCHEMA_VERSION:
        errors.append(
            f"Unexpected schema_version: {data['schema_version']!r} "
            f"(expected {REPORT_SCHEMA_VERSION!r})"
        )

    if "report_type" in data and data["report_type"] != "backtest_research_summary":
        errors.append(f"Unexpected report_type: {data['report_type']!r}")

    if "status" in data and data["status"] not in ALLOWED_STATUSES:
        errors.append(
            f"Unexpected status: {data['status']!r} (expected one of {ALLOWED_STATUSES})"
        )

    if "run_id" in data:
        if not isinstance(data["run_id"], str) or not data["run_id"]:
            errors.append("run_id must be a non-empty string")

    # Metrics
    if "metrics" in data:
        metrics = data["metrics"]
        if not isinstance(metrics, dict):
            errors.append("metrics must be an object")
        else:
            missing_metrics = REQUIRED_METRIC_KEYS - set(metrics.keys())
            if missing_metrics:
                errors.append(f"Missing metric keys: {sorted(missing_metrics)}")
            for key in REQUIRED_METRIC_KEYS:
                if key in metrics and not isinstance(metrics[key], (int, float)):
                    errors.append(f"metrics.{key} must be numeric")

    # Config
    if "config" in data:
        config = data["config"]
        if not isinstance(config, dict):
            errors.append("config must be an object")
        else:
            missing_config = REQUIRED_CONFIG_KEYS - set(config.keys())
            if missing_config:
                errors.append(f"Missing config keys: {sorted(missing_config)}")

    # Fills
    if "fills" in data:
        fills = data["fills"]
        if not isinstance(fills, list):
            errors.append("fills must be an array")
        else:
            for i, fill in enumerate(fills):
                if not isinstance(fill, dict):
                    errors.append(f"fills[{i}] must be an object")
                    continue
                for key in ("side", "symbol", "quantity", "price", "notional"):
                    if key not in fill:
                        errors.append(f"fills[{i}] missing key: {key}")
                if fill.get("side") not in {"buy", "sell"}:
                    errors.append(
                        f"fills[{i}].side must be 'buy' or 'sell', got {fill.get('side')!r}"
                    )

    # Equity curve
    if "equity_curve" in data:
        equity_curve = data["equity_curve"]
        if not isinstance(equity_curve, list):
            errors.append("equity_curve must be an array")
        else:
            for i, point in enumerate(equity_curve):
                if not isinstance(point, dict):
                    errors.append(f"equity_curve[{i}] must be an object")
                    continue
                if "timestamp" not in point or "equity" not in point:
                    errors.append(
                        f"equity_curve[{i}] missing 'timestamp' or 'equity'"
                    )

    # Strategy metadata
    if "strategy_metadata" in data:
        strategy_metadata = data["strategy_metadata"]
        if not isinstance(strategy_metadata, dict):
            errors.append("strategy_metadata must be an object")
        elif "strategy_id" not in strategy_metadata:
            errors.append("strategy_metadata missing 'strategy_id'")

    # Diagnostics
    if "diagnostics" in data:
        diagnostics = data["diagnostics"]
        if not isinstance(diagnostics, dict):
            errors.append("diagnostics must be an object")

    return errors


def validate_backtest_report(data: dict[str, Any]) -> None:
    """Validate a backtest report dict against the schema contract.

    Raises:
        ReportSchemaError: On any structural or type violation.
    """
    if not isinstance(data, dict):
        raise ReportSchemaError("Report must be a JSON object (dict)")

    # Top-level keys
    missing_top = REQUIRED_TOP_LEVEL_KEYS - set(data.keys())
    if missing_top:
        raise ReportSchemaError(f"Missing top-level keys: {sorted(missing_top)}")

    if data["schema_version"] != REPORT_SCHEMA_VERSION:
        raise ReportSchemaError(
            f"Unexpected schema_version: {data['schema_version']!r} "
            f"(expected {REPORT_SCHEMA_VERSION!r})"
        )

    if data["report_type"] != "backtest_research_summary":
        raise ReportSchemaError(
            f"Unexpected report_type: {data['report_type']!r}"
        )

    if data["status"] not in ALLOWED_STATUSES:
        raise ReportSchemaError(
            f"Unexpected status: {data['status']!r} (expected one of {ALLOWED_STATUSES})"
        )

    if not isinstance(data["run_id"], str) or not data["run_id"]:
        raise ReportSchemaError("run_id must be a non-empty string")

    # Metrics
    metrics = data["metrics"]
    if not isinstance(metrics, dict):
        raise ReportSchemaError("metrics must be an object")
    missing_metrics = REQUIRED_METRIC_KEYS - set(metrics.keys())
    if missing_metrics:
        raise ReportSchemaError(f"Missing metric keys: {sorted(missing_metrics)}")
    for key in REQUIRED_METRIC_KEYS:
        if not isinstance(metrics[key], (int, float)):
            raise ReportSchemaError(f"metrics.{key} must be numeric")

    # Config
    config = data["config"]
    if not isinstance(config, dict):
        raise ReportSchemaError("config must be an object")
    missing_config = REQUIRED_CONFIG_KEYS - set(config.keys())
    if missing_config:
        raise ReportSchemaError(f"Missing config keys: {sorted(missing_config)}")

    # Fills
    fills = data["fills"]
    if not isinstance(fills, list):
        raise ReportSchemaError("fills must be an array")
    for i, fill in enumerate(fills):
        if not isinstance(fill, dict):
            raise ReportSchemaError(f"fills[{i}] must be an object")
        for key in ("side", "symbol", "quantity", "price", "notional"):
            if key not in fill:
                raise ReportSchemaError(f"fills[{i}] missing key: {key}")
        if fill.get("side") not in {"buy", "sell"}:
            raise ReportSchemaError(
                f"fills[{i}].side must be 'buy' or 'sell', got {fill.get('side')!r}"
            )

    # Equity curve
    equity_curve = data["equity_curve"]
    if not isinstance(equity_curve, list):
        raise ReportSchemaError("equity_curve must be an array")
    for i, point in enumerate(equity_curve):
        if not isinstance(point, dict):
            raise ReportSchemaError(f"equity_curve[{i}] must be an object")
        if "timestamp" not in point or "equity" not in point:
            raise ReportSchemaError(
                f"equity_curve[{i}] missing 'timestamp' or 'equity'"
            )

    # Strategy metadata
    strategy_metadata = data["strategy_metadata"]
    if not isinstance(strategy_metadata, dict):
        raise ReportSchemaError("strategy_metadata must be an object")
    if "strategy_id" not in strategy_metadata:
        raise ReportSchemaError("strategy_metadata missing 'strategy_id'")

    # Diagnostics
    diagnostics = data["diagnostics"]
    if not isinstance(diagnostics, dict):
        raise ReportSchemaError("diagnostics must be an object")


def get_schema_status(data: Any) -> str:
    """Return the schema validation status for a raw report dict.

    Returns one of:
      - "valid"                – passes validate_backtest_report
      - "legacy"               – missing schema_version key
      - "unreadable"           – not a dict / not JSON-parseable
      - "invalid: <reason>"    – has schema_version but fails validation
    """
    if not isinstance(data, dict):
        return "unreadable"
    if "schema_version" not in data:
        return "legacy"
    errors = collect_backtest_report_schema_errors(data)
    if not errors:
        return "valid"
    return f"invalid: {errors[0]}"


def validate_backtest_result(result: "BacktestResult") -> dict[str, Any]:
    """Validate a BacktestResult and return the report dict with schema_version.

    This is a convenience wrapper that renders the JSON report and then
    validates it, ensuring the engine → report pipeline is contract-safe.
    """
    from atlas_agent.backtest.report import render_json_report

    report = render_json_report(result)
    validate_backtest_report(report)
    return report
