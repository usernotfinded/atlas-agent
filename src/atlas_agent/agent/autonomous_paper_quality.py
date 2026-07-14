# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    agent/autonomous_paper_quality.py
# PURPOSE: Judges whether an autonomous paper run was any GOOD — not merely whether
#          it made money. A run that profited by breaching its own discipline is a
#          failure here, because the next one would lose the same way.
# DEPS:    agent.autonomous_paper_models
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atlas_agent.agent.autonomous_paper_metrics import calculate_stateful_paper_metrics
from atlas_agent.backtest.data import load_market_data
from atlas_agent.backtest.models import BacktestFill, BacktestPosition


@dataclass(frozen=True)
class TradingQualityThresholdPolicy:
    """Conservative, configurable thresholds for the trading-quality gate.

    Defaults are chosen for tests/demo and do not require profitability.
    """

    min_bars_processed: int = 10
    min_fills: int = 1
    min_no_trade_decisions: int = 1
    min_risk_rejections: int = 1
    max_drawdown_pct: float = 50.0
    max_exposure_pct: float = 200.0
    max_turnover: float = 100.0
    max_cost_impact_pct: float = 10.0
    min_data_coverage: float = 0.5
    max_invalid_metric_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_bars_processed": self.min_bars_processed,
            "min_fills": self.min_fills,
            "min_no_trade_decisions": self.min_no_trade_decisions,
            "min_risk_rejections": self.min_risk_rejections,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_exposure_pct": self.max_exposure_pct,
            "max_turnover": self.max_turnover,
            "max_cost_impact_pct": self.max_cost_impact_pct,
            "min_data_coverage": self.min_data_coverage,
            "max_invalid_metric_count": self.max_invalid_metric_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TradingQualityThresholdPolicy:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


def _load_json(path: str | Path, label: str) -> tuple[dict[str, Any] | None, list[str]]:
    p = Path(path)
    if not p.is_file():
        return None, [f"{label} file not found: {p.name}"]
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as exc:
        return None, [f"Failed to read {label} file: {exc}"]
    if not text.strip():
        return None, [f"{label} file is empty."]
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [f"{label} is not valid JSON: {exc}"]
    if not isinstance(obj, dict):
        return None, [f"{label} is not a JSON object."]
    return obj, []


def _load_jsonl(path: str | Path, label: str) -> tuple[list[dict[str, Any]], list[str]]:
    p = Path(path)
    if not p.is_file():
        return [], [f"{label} file not found: {p.name}"]
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as exc:
        return [], [f"Failed to read {label} file: {exc}"]
    if not text.strip():
        return [], []
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{label} line {line_number}: invalid JSON ({exc})")
            continue
        if not isinstance(obj, dict):
            errors.append(f"{label} line {line_number}: not a JSON object")
            continue
        rows.append(obj)
    return rows, errors


def _load_artifacts(
    *,
    metrics_path: str | Path,
    decisions_path: str | Path,
    fills_path: str | Path,
    state_path: str | Path | None = None,
    scorecard_path: str | Path | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None, dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    metrics, m_errs = _load_json(metrics_path, "metrics")
    errors.extend(m_errs)
    decisions, d_errs = _load_jsonl(decisions_path, "decisions")
    errors.extend(d_errs)
    fills, f_errs = _load_jsonl(fills_path, "fills")
    errors.extend(f_errs)
    state = None
    if state_path:
        state, s_errs = _load_json(state_path, "state")
        errors.extend(s_errs)
    scorecard = None
    if scorecard_path:
        scorecard, sc_errs = _load_json(scorecard_path, "scorecard")
        errors.extend(sc_errs)
    return metrics, decisions, fills, state, scorecard, errors


QUALITY_STATES = (
    "not_evaluated",
    "blocked",
    "paper_activity_observed",
    "paper_quality_reviewable",
    "eligible_for_shadow_live_quality_review",
)

DIMENSIONS = (
    "artifact_integrity",
    "stateful_resume_integrity",
    "trade_activity",
    "risk_rejection_coverage",
    "no_trade_coverage",
    "cost_accounting",
    "drawdown_bounds",
    "return_bounds",
    "exposure_bounds",
    "turnover_bounds",
    "benchmark_comparison",
    "replay_or_recompute_consistency",
    "data_coverage",
    "metric_validity",
    "no_live_side_effects",
)

LIVE_SIDE_EFFECT_PATTERNS = (
    "live_trading_enabled",
    "broker.submit",
    "provider.execute",
    "broker.execute",
    "provider.submit",
    "place_order(",
    "cancel_order(",
    "flatten_all(",
)

SECRET_LIKE_PATTERNS = (
    "api_key",
    "apikey",
    "token",
    "password",
    "secret",
    "credential",
    "private_key",
    "privatekey",
    "auth_header",
    "bearer ",
    "ghp_",
    "sk-",
)


def _artifact_text(*artifacts: Any) -> str:
    parts: list[str] = []
    for artifact in artifacts:
        if artifact is None:
            continue
        if isinstance(artifact, list):
            parts.extend(json.dumps(item, sort_keys=True) for item in artifact)
        else:
            parts.append(json.dumps(artifact, sort_keys=True))
    return "\n".join(parts)


def _count_decisions_by_state(decisions: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for d in decisions:
        state = str(d.get("decision_state", "unknown"))
        counts[state] = counts.get(state, 0) + 1
    return counts


def _is_finite(value: Any) -> bool:
    if value is None:
        return False
    try:
        return bool(math.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        f = float(value)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def _has_pattern(text: str, patterns: tuple[str, ...]) -> tuple[bool, str]:
    lowered = text.lower()
    for pattern in patterns:
        if pattern in lowered:
            return True, f"Artifact text contains pattern: {pattern!r}"
    return False, ""


def _dimension(name: str, passed: bool, score: float, reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "score": float(max(0.0, min(1.0, score))),
        "reason": reason,
    }


def _compute_benchmark(
    *,
    data_path: str | Path | None,
    starting_cash: float,
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute a deterministic buy-and-hold benchmark if data is available."""
    if data_path is None:
        return {
            "available": False,
            "reason": "No data_path provided; benchmark unavailable.",
            "strategy_total_return_pct": None,
            "benchmark_total_return_pct": None,
            "excess_return_pct": None,
        }
    try:
        bars = list(load_market_data(str(data_path)))
    except Exception as exc:
        return {
            "available": False,
            "reason": f"Failed to load market data: {exc}",
            "strategy_total_return_pct": None,
            "benchmark_total_return_pct": None,
            "excess_return_pct": None,
        }
    if not bars:
        return {
            "available": False,
            "reason": "Market data is empty.",
            "strategy_total_return_pct": None,
            "benchmark_total_return_pct": None,
            "excess_return_pct": None,
        }

    if decisions:
        first_idx = min(
            (d.get("bar_index", 0) for d in decisions if isinstance(d.get("bar_index"), int)),
            default=0,
        )
        last_idx = max(
            (d.get("bar_index", 0) for d in decisions if isinstance(d.get("bar_index"), int)),
            default=len(bars) - 1,
        )
    else:
        first_idx = 0
        last_idx = len(bars) - 1

    if first_idx < 0 or last_idx >= len(bars) or first_idx >= last_idx:
        return {
            "available": False,
            "reason": "Decision window does not overlap with market data.",
            "strategy_total_return_pct": None,
            "benchmark_total_return_pct": None,
            "excess_return_pct": None,
        }

    start_price = float(bars[first_idx].close)
    end_price = float(bars[last_idx].close)
    if start_price <= 0:
        return {
            "available": False,
            "reason": "Start price non-positive; cannot compute benchmark.",
            "strategy_total_return_pct": None,
            "benchmark_total_return_pct": None,
            "excess_return_pct": None,
        }

    benchmark_return_pct = (end_price - start_price) / start_price * 100.0

    return {
        "available": True,
        "reason": "Buy-and-hold benchmark computed over evaluated bar window.",
        "strategy_total_return_pct": None,
        "benchmark_total_return_pct": benchmark_return_pct,
        "excess_return_pct": None,
    }


def _recompute_and_compare_metrics(
    *,
    metrics: dict[str, Any],
    fills: list[dict[str, Any]],
    state: dict[str, Any] | None,
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Recompute metrics from fills/state and compare to provided metrics."""
    if not fills:
        return {
            "consistent": False,
            "reason": "No fills available for recomputation.",
            "recomputed": None,
        }

    def _normalize_fill(index: int, fill: dict[str, Any]) -> dict[str, Any]:
        defaults = {
            "fill_id": f"fill-{index}",
            "order_id": f"order-{index}",
            "timestamp": fill.get("timestamp", "1970-01-01T00:00:00Z"),
            "symbol": fill.get("symbol", "DEMO-SYMBOL"),
        }
        return {**defaults, **fill}

    try:
        fill_history = [
            BacktestFill(**_normalize_fill(i, f)) for i, f in enumerate(fills)
        ]
    except Exception as exc:
        return {
            "consistent": False,
            "reason": f"Could not parse fills: {exc}",
            "recomputed": None,
        }

    starting_cash = _safe_float(metrics.get("starting_cash"), 1.0)
    cash = _safe_float(metrics.get("ending_cash"), starting_cash)
    bars_processed = int(metrics.get("bars_processed", 0))
    current_price = 1.0
    if fill_history:
        current_price = float(fill_history[-1].price)

    positions: dict[str, BacktestPosition] = {}
    if state and isinstance(state.get("positions"), dict):
        try:
            for symbol, pos in state["positions"].items():
                positions[symbol] = BacktestPosition(**pos)
        except Exception as exc:
            return {
                "consistent": False,
                "reason": f"Could not parse positions: {exc}",
                "recomputed": None,
            }

    number_of_rejections = int(metrics.get("number_of_rejections", 0))
    data_source = metrics.get("data_source_redacted", "unknown")

    try:
        recomputed = calculate_stateful_paper_metrics(
            starting_cash=starting_cash,
            cash=cash,
            positions=positions,
            fill_history=fill_history,
            bars_processed=bars_processed,
            current_price=current_price,
            data_source=data_source,
            number_of_rejections=number_of_rejections,
        )
        # Pin the generated timestamp so the recomputed output is deterministic
        # for audit/replay reproducibility.
        recomputed.generated_at = str(metrics.get("generated_at", "1970-01-01T00:00:00Z"))
    except Exception as exc:
        return {
            "consistent": False,
            "reason": f"Recomputation failed: {exc}",
            "recomputed": None,
        }

    tolerance = 1e-6
    fields = [
        ("total_return_pct", recomputed.total_return_pct),
        ("max_drawdown_pct", abs(recomputed.max_drawdown_pct)),
        ("number_of_fills", float(recomputed.number_of_fills)),
        ("total_commission", recomputed.total_commission),
        ("total_slippage", recomputed.total_slippage),
    ]
    mismatches: list[str] = []
    for name, recomputed_value in fields:
        provided = _safe_float(metrics.get(name), 0.0)
        if name == "max_drawdown_pct":
            provided = abs(provided)
        if name == "number_of_fills":
            provided = float(metrics.get(name, 0))
        diff = abs(provided - recomputed_value)
        threshold = max(abs(provided), 1.0)
        if diff > tolerance and diff / threshold > tolerance:
            mismatches.append(f"{name}: provided={provided}, recomputed={recomputed_value}")

    if mismatches:
        return {
            "consistent": False,
            "reason": "Metric mismatch: " + "; ".join(mismatches),
            "recomputed": recomputed.model_dump(),
        }

    return {
        "consistent": True,
        "reason": "Recomputed metrics match provided metrics within tolerance.",
        "recomputed": recomputed.model_dump(),
    }


def _evaluate_dimensions(
    *,
    metrics: dict[str, Any],
    decisions: list[dict[str, Any]],
    fills: list[dict[str, Any]],
    state: dict[str, Any] | None,
    scorecard: dict[str, Any] | None,
    policy: TradingQualityThresholdPolicy,
    benchmark: dict[str, Any] | None,
    consistency: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    dimensions: list[dict[str, Any]] = []
    decision_counts = _count_decisions_by_state(decisions)
    no_trade_count = decision_counts.get("no_trade", 0)
    risk_blocked_count = decision_counts.get("risk_blocked", 0)
    fill_count = len(fills)
    bars_processed = int(metrics.get("bars_processed", 0))
    total_return_pct = _safe_float(metrics.get("total_return_pct"), 0.0)
    max_drawdown_pct = abs(_safe_float(metrics.get("max_drawdown_pct"), 0.0))
    gross_exposure = abs(_safe_float(metrics.get("gross_exposure"), 0.0))
    net_exposure = abs(_safe_float(metrics.get("net_exposure"), 0.0))
    turnover = _safe_float(metrics.get("turnover"), 0.0)
    total_commission = _safe_float(metrics.get("total_commission"), 0.0)
    total_slippage = _safe_float(metrics.get("total_slippage"), 0.0)
    ending_equity = _safe_float(metrics.get("ending_equity"), 0.0)
    starting_cash = _safe_float(metrics.get("starting_cash"), 1.0)

    invalid_metrics: list[str] = []
    for key, value in metrics.items():
        if isinstance(value, float) and not _is_finite(value):
            invalid_metrics.append(key)

    text = _artifact_text(metrics, decisions, fills, state, scorecard)

    # artifact_integrity
    artifact_errors: list[str] = []
    required_metric_fields = [
        "run_id", "starting_cash", "ending_equity", "total_return_pct",
        "max_drawdown_pct", "number_of_fills", "number_of_rejections",
        "gross_exposure", "net_exposure", "total_commission", "total_slippage",
        "bars_processed",
    ]
    missing = [f for f in required_metric_fields if f not in metrics]
    if missing:
        artifact_errors.append(f"metrics missing fields: {missing}")
    if not decisions:
        artifact_errors.append("decisions file is empty or missing")
    if not fills:
        artifact_errors.append("fills file is empty or missing")
    dimensions.append(_dimension(
        "artifact_integrity",
        not artifact_errors,
        1.0 if not artifact_errors else 0.0,
        "Required artifacts and fields present." if not artifact_errors else "; ".join(artifact_errors),
    ))

    # stateful_resume_integrity
    if state is None:
        state_ok = True
        state_reason = "No state artifact provided (optional)."
    else:
        cursor = state.get("cursor", {})
        if (
            isinstance(cursor, dict)
            and isinstance(cursor.get("last_processed_bar_index"), int)
            and cursor.get("last_processed_bar_index", -2) >= -1
            and state.get("run_id") == metrics.get("run_id")
        ):
            state_ok = True
            state_reason = "State schema and identity are consistent."
        else:
            state_ok = False
            state_reason = "State schema invalid or run_id mismatch."
    dimensions.append(_dimension("stateful_resume_integrity", state_ok, 1.0 if state_ok else 0.0, state_reason))

    # trade_activity
    trade_ok = fill_count >= policy.min_fills
    dimensions.append(_dimension(
        "trade_activity",
        trade_ok,
        1.0 if trade_ok else 0.0,
        f"Fills: {fill_count} (required >= {policy.min_fills}).",
    ))

    # risk_rejection_coverage
    risk_ok = risk_blocked_count >= policy.min_risk_rejections
    dimensions.append(_dimension(
        "risk_rejection_coverage",
        risk_ok,
        1.0 if risk_ok else 0.0,
        f"Risk rejections: {risk_blocked_count} (required >= {policy.min_risk_rejections}).",
    ))

    # no_trade_coverage
    no_trade_ok = no_trade_count >= policy.min_no_trade_decisions
    dimensions.append(_dimension(
        "no_trade_coverage",
        no_trade_ok,
        1.0 if no_trade_ok else 0.0,
        f"No-trade decisions: {no_trade_count} (required >= {policy.min_no_trade_decisions}).",
    ))

    # cost_accounting
    cost_impact_pct = (
        (total_commission + total_slippage) / ending_equity * 100.0
        if ending_equity > 0
        else 0.0
    )
    cost_ok = (
        total_commission >= 0
        and total_slippage >= 0
        and cost_impact_pct <= policy.max_cost_impact_pct
    )
    dimensions.append(_dimension(
        "cost_accounting",
        cost_ok,
        1.0 if cost_ok else 0.0,
        (
            f"Commission={total_commission}, slippage={total_slippage}, "
            f"cost_impact_pct={cost_impact_pct:.4f}% (limit {policy.max_cost_impact_pct}%)."
        ),
    ))

    # drawdown_bounds
    dd_ok = max_drawdown_pct <= policy.max_drawdown_pct
    dimensions.append(_dimension(
        "drawdown_bounds",
        dd_ok,
        1.0 if dd_ok else 0.0,
        f"Max drawdown: {max_drawdown_pct:.4f}% (limit {policy.max_drawdown_pct}%).",
    ))

    # return_bounds
    return_ok = _is_finite(metrics.get("total_return_pct")) and abs(total_return_pct) <= 100.0
    dimensions.append(_dimension(
        "return_bounds",
        return_ok,
        1.0 if return_ok else 0.0,
        f"Total return: {total_return_pct:.4f}%.",
    ))

    # exposure_bounds
    exposure_pct = (max(gross_exposure, abs(net_exposure)) / starting_cash) * 100.0 if starting_cash > 0 else 0.0
    exposure_ok = exposure_pct <= policy.max_exposure_pct
    dimensions.append(_dimension(
        "exposure_bounds",
        exposure_ok,
        1.0 if exposure_ok else 0.0,
        f"Exposure: {exposure_pct:.4f}% (limit {policy.max_exposure_pct}%).",
    ))

    # turnover_bounds
    turnover_ok = turnover <= policy.max_turnover
    dimensions.append(_dimension(
        "turnover_bounds",
        turnover_ok,
        1.0 if turnover_ok else 0.0,
        f"Turnover: {turnover:.4f} (limit {policy.max_turnover}).",
    ))

    # benchmark_comparison
    if benchmark:
        dimensions.append(_dimension(
            "benchmark_comparison",
            benchmark.get("available", False),
            1.0 if benchmark.get("available", False) else 0.0,
            benchmark.get("reason", "Benchmark evaluated."),
        ))
    else:
        dimensions.append(_dimension(
            "benchmark_comparison",
            True,
            1.0,
            "Benchmark comparison not required by default policy.",
        ))

    # replay_or_recompute_consistency
    if consistency is None:
        dimensions.append(_dimension(
            "replay_or_recompute_consistency",
            True,
            1.0,
            "Metric recomputation not performed (optional).",
        ))
    else:
        consistency_ok = consistency.get("consistent", False)
        dimensions.append(_dimension(
            "replay_or_recompute_consistency",
            consistency_ok,
            1.0 if consistency_ok else 0.0,
            consistency.get("reason", "Consistency evaluated."),
        ))

    # data_coverage
    expected_bars = max(len(decisions), policy.min_bars_processed)
    coverage = bars_processed / expected_bars if expected_bars > 0 else 0.0
    data_ok = (
        bars_processed >= policy.min_bars_processed
        and coverage >= policy.min_data_coverage
    )
    dimensions.append(_dimension(
        "data_coverage",
        data_ok,
        1.0 if data_ok else 0.0,
        (
            f"Bars processed: {bars_processed} (required >= {policy.min_bars_processed}); "
            f"coverage: {coverage:.2%} (required >= {policy.min_data_coverage:.0%})."
        ),
    ))

    # metric_validity
    metric_ok = len(invalid_metrics) <= policy.max_invalid_metric_count
    dimensions.append(_dimension(
        "metric_validity",
        metric_ok,
        1.0 if metric_ok else 0.0,
        f"Invalid metrics: {invalid_metrics} (limit {policy.max_invalid_metric_count}).",
    ))

    # no_live_side_effects
    has_live, live_reason = _has_pattern(text, LIVE_SIDE_EFFECT_PATTERNS)
    has_secret, secret_reason = _has_pattern(text, SECRET_LIKE_PATTERNS)
    side_effect_ok = not has_live and not has_secret
    reasons = []
    if has_live:
        reasons.append(live_reason)
    if has_secret:
        reasons.append(secret_reason)
    dimensions.append(_dimension(
        "no_live_side_effects",
        side_effect_ok,
        1.0 if side_effect_ok else 0.0,
        "; ".join(reasons) if reasons else "No live side-effect or secret-like patterns detected.",
    ))

    return dimensions


def _redact_path(path: str | Path | None) -> str | None:
    if path is None:
        return None
    p = Path(path)
    try:
        rel = p.relative_to(Path.cwd())
        return str(rel)
    except ValueError:
        return p.name


def _redact_report(report: dict[str, Any]) -> dict[str, Any]:
    report = dict(report)
    inputs = report.get("input_artifacts", {})
    report["input_artifacts"] = {
        k: _redact_path(v) if isinstance(v, str) else v for k, v in inputs.items()
    }
    return report


def write_trading_quality_artifacts(
    report: dict[str, Any],
    output_dir: str | Path,
) -> tuple[Path, Path]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = _redact_report(report)
    json_path = out / "trading-quality-gate.json"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    md_path = out / "trading-quality-report.md"
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return json_path, md_path


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Trading Quality Gate Report",
        "",
        f"**Run ID:** {report.get('run_id', 'unknown')}",
        f"**Symbol:** {report.get('symbol', 'unknown')}",
        f"**Quality State:** `{report.get('quality_state', 'unknown')}`",
        f"**Mode:** {report.get('mode', 'unknown')}",
        "",
        "> **Disclaimer:** This is a paper-only evaluation. It does not claim profitability, live readiness, or autonomous live trading readiness.",
        "",
        "## Input Artifacts",
        "",
    ]
    for key, value in report.get("input_artifacts", {}).items():
        lines.append(f"- **{key}:** `{value}`")
    lines.append("")
    lines.append("## Threshold Policy")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report.get("threshold_policy", {}), indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("## Metrics")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report.get("metrics"), indent=2, sort_keys=True, default=str))
    lines.append("```")
    lines.append("")
    lines.append("## Benchmark Comparison")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report.get("benchmark"), indent=2, sort_keys=True, default=str))
    lines.append("```")
    lines.append("")
    lines.append("## Dimensions")
    lines.append("")
    lines.append("| Dimension | Passed | Score | Reason |")
    lines.append("|-----------|--------|-------|--------|")
    for d in report.get("dimensions", []):
        passed = "✅" if d["passed"] else "❌"
        lines.append(f"| {d['name']} | {passed} | {d['score']} | {d['reason']} |")
    lines.append("")
    if report.get("blockers"):
        lines.append("## Blockers")
        lines.append("")
        for blocker in report["blockers"]:
            lines.append(f"- {blocker}")
        lines.append("")
    return "\n".join(lines)


def _resolve_symbol(
    *,
    explicit_symbol: str | None,
    metrics: dict[str, Any] | None,
    state: dict[str, Any] | None,
    decisions: list[dict[str, Any]],
    fills: list[dict[str, Any]],
) -> tuple[str | None, list[str]]:
    """Resolve the evaluated trading symbol from the most reliable source.

    Resolution order:
      1. Explicitly supplied symbol parameter.
      2. ``symbol`` field in the state artifact.
      3. ``symbol`` field in the metrics object.
      4. A single symbol in state positions.
      5. A single consistent symbol across fills.
      6. A single consistent symbol across decisions.

    The CSV/data-source filename is never used as a symbol.
    """
    if explicit_symbol and isinstance(explicit_symbol, str):
        return explicit_symbol, []

    if state is not None:
        state_symbol = state.get("symbol")
        if isinstance(state_symbol, str) and state_symbol.strip():
            return state_symbol, []

    if metrics is not None:
        metrics_symbol = metrics.get("symbol")
        if isinstance(metrics_symbol, str) and metrics_symbol.strip():
            return metrics_symbol, []

    if state is not None:
        positions = state.get("positions")
        if isinstance(positions, dict):
            position_symbols = {
                s for s in positions.keys()
                if isinstance(s, str) and s.strip()
            }
            if len(position_symbols) == 1:
                return position_symbols.pop(), []

    fill_symbols = {
        f.get("symbol")
        for f in fills
        if isinstance(f.get("symbol"), str) and f["symbol"].strip()
    }
    if len(fill_symbols) == 1:
        return fill_symbols.pop(), []

    decision_symbols = {
        d.get("symbol")
        for d in decisions
        if isinstance(d.get("symbol"), str) and d["symbol"].strip()
    }
    if len(decision_symbols) == 1:
        return decision_symbols.pop(), []

    return None, ["symbol could not be resolved from state, metrics, fills, or decisions"]


def build_trading_quality_gate(
    *,
    metrics_path: str | Path,
    decisions_path: str | Path,
    fills_path: str | Path,
    state_path: str | Path | None = None,
    scorecard_path: str | Path | None = None,
    data_path: str | Path | None = None,
    policy: TradingQualityThresholdPolicy | None = None,
    symbol: str | None = None,
) -> dict[str, Any]:
    policy = policy or TradingQualityThresholdPolicy()
    metrics, decisions, fills, state, scorecard, load_errors = _load_artifacts(
        metrics_path=metrics_path,
        decisions_path=decisions_path,
        fills_path=fills_path,
        state_path=state_path,
        scorecard_path=scorecard_path,
    )

    if load_errors or metrics is None:
        return {
            "artifact_type": "trading_quality_gate",
            "schema_version": 1,
            "mode": "paper",
            "quality_state": "not_evaluated",
            "blockers": load_errors or ["metrics.json is required."],
            "dimensions": [],
            "metrics": metrics,
            "benchmark": None,
            "threshold_policy": policy.to_dict(),
            "run_id": metrics.get("run_id") if metrics else None,
            "symbol": None,
            "disclaimer": "This is a paper-only evaluation. It does not claim profitability or live readiness.",
        }

    resolved_symbol, symbol_errors = _resolve_symbol(
        explicit_symbol=symbol,
        metrics=metrics,
        state=state,
        decisions=decisions,
        fills=fills,
    )
    if symbol_errors:
        return {
            "artifact_type": "trading_quality_gate",
            "schema_version": 1,
            "mode": "paper",
            "run_id": metrics.get("run_id"),
            "symbol": None,
            "quality_state": "blocked",
            "blockers": symbol_errors,
            "dimensions": [],
            "metrics": metrics,
            "benchmark": None,
            "threshold_policy": policy.to_dict(),
            "input_artifacts": {
                "metrics": Path(metrics_path).name,
                "decisions": Path(decisions_path).name,
                "fills": Path(fills_path).name,
                "state": Path(state_path).name if state_path else None,
                "scorecard": Path(scorecard_path).name if scorecard_path else None,
            },
            "disclaimer": "This is a paper-only evaluation. It does not claim profitability or live readiness.",
        }

    benchmark = _compute_benchmark(
        data_path=data_path,
        starting_cash=_safe_float(metrics.get("starting_cash"), 1.0),
        decisions=decisions,
    )
    if benchmark.get("available") and _is_finite(metrics.get("total_return_pct")):
        strategy_return = _safe_float(metrics.get("total_return_pct"), 0.0)
        benchmark_return = _safe_float(benchmark.get("benchmark_total_return_pct"), 0.0)
        benchmark["strategy_total_return_pct"] = strategy_return
        benchmark["excess_return_pct"] = strategy_return - benchmark_return

    consistency = _recompute_and_compare_metrics(
        metrics=metrics,
        fills=fills,
        state=state,
        decisions=decisions,
    )

    dimensions = _evaluate_dimensions(
        metrics=metrics,
        decisions=decisions,
        fills=fills,
        state=state,
        scorecard=scorecard,
        policy=policy,
        benchmark=benchmark if benchmark.get("available") else None,
        consistency=consistency,
    )

    dimension_map = {d["name"]: d for d in dimensions}
    blockers = [d["reason"] for d in dimensions if not d["passed"]]

    quality_state = "blocked"
    if not dimensions:
        quality_state = "not_evaluated"
    elif blockers:
        quality_state = "blocked"
    elif (
        dimension_map["trade_activity"]["passed"]
        and dimension_map["risk_rejection_coverage"]["passed"]
        and dimension_map["no_trade_coverage"]["passed"]
        and dimension_map["drawdown_bounds"]["passed"]
        and dimension_map["exposure_bounds"]["passed"]
        and dimension_map["turnover_bounds"]["passed"]
        and dimension_map["metric_validity"]["passed"]
        and dimension_map["artifact_integrity"]["passed"]
        and dimension_map["no_live_side_effects"]["passed"]
    ):
        quality_state = "eligible_for_shadow_live_quality_review"
    elif dimension_map["trade_activity"]["passed"]:
        quality_state = "paper_quality_reviewable"
    else:
        quality_state = "paper_activity_observed"

    return {
        "artifact_type": "trading_quality_gate",
        "schema_version": 1,
        "mode": "paper",
        "run_id": metrics.get("run_id"),
        "symbol": resolved_symbol,
        "quality_state": quality_state,
        "blockers": blockers,
        "dimensions": dimensions,
        "metrics": metrics,
        "benchmark": benchmark,
        "threshold_policy": policy.to_dict(),
        "input_artifacts": {
            "metrics": Path(metrics_path).name,
            "decisions": Path(decisions_path).name,
            "fills": Path(fills_path).name,
            "state": Path(state_path).name if state_path else None,
            "scorecard": Path(scorecard_path).name if scorecard_path else None,
        },
        "disclaimer": "This is a paper-only evaluation. It does not claim profitability or live readiness.",
    }
