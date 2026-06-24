from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
        return [], [f"{label} file is empty."]
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


def build_trading_quality_gate(
    *,
    metrics_path: str | Path,
    decisions_path: str | Path,
    fills_path: str | Path,
    state_path: str | Path | None = None,
    scorecard_path: str | Path | None = None,
    data_path: str | Path | None = None,
    policy: TradingQualityThresholdPolicy | None = None,
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
            "metrics": None,
            "benchmark": None,
            "threshold_policy": policy.to_dict(),
            "run_id": None,
            "disclaimer": "This is a paper-only evaluation. It does not claim profitability or live readiness.",
        }

    return {
        "artifact_type": "trading_quality_gate",
        "schema_version": 1,
        "mode": "paper",
        "quality_state": "blocked",
        "blockers": ["not yet implemented"],
        "dimensions": [],
        "metrics": metrics,
        "benchmark": None,
        "threshold_policy": policy.to_dict(),
        "run_id": metrics.get("run_id"),
        "disclaimer": "This is a paper-only evaluation. It does not claim profitability or live readiness.",
    }
