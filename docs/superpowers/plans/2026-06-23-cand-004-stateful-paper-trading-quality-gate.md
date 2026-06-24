# CAND-004: Stateful Paper Trading Quality Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, fail-closed trading-quality gate for stateful autonomous paper runs that evaluates trading behavior separately from artifact hygiene.

**Architecture:** A single new module `autonomous_paper_quality.py` exposes a threshold policy, a gate builder, and artifact writers. A new CLI command `atlas agent autonomous-paper-quality` reads runner artifacts and emits `trading-quality-gate.json` and `trading-quality-report.md`. A contract checker enforces safety boundaries. CAND-002 scorecard is left untouched.

**Tech Stack:** Python 3.11, Pydantic, existing `calculate_stateful_paper_metrics`, `calculate_metrics`, `BacktestFill`, `BacktestPosition`, `StatefulPaperMetrics`, `StatefulPaperState`.

---

## File Map

| File | Responsibility |
|------|----------------|
| `src/atlas_agent/agent/autonomous_paper_quality.py` | Policy, gate builder, metric recomputation, benchmark, artifact writers |
| `src/atlas_agent/cli.py` | Register `atlas agent autonomous-paper-quality` and dispatch |
| `scripts/check_autonomous_paper_quality_contract.py` | Static contract/safety checker |
| `tests/test_autonomous_paper_quality.py` | Feature tests |
| `tests/test_autonomous_paper_quality_contract.py` | Checker tests |
| `tests/fixtures/cli_command_contract.json` | Add new agent subcommand |
| `docs/autonomous-paper-quality-gate.md` | User-facing spec |
| `docs/releases/v0.6.16-candidates.json` | Mark CAND-004 implemented |
| `docs/releases/v0.6.16-candidates.md` | Human-readable candidate list |
| `docs/releases/v0.6.16-candidate-selection.md` | Eligibility note |
| `docs/releases/v0.6.16-plan.md` | Candidate table |
| `docs/bounded-live-autonomy-governance.md` | Add CAND-004 truth line |
| `CHANGELOG.md` | Unreleased entry |
| `scripts/dev_check.sh` | Add checker + focused pytest blocks |
| `scripts/release_check.sh` | Add checker + focused pytest blocks |
| `scripts/demo_autonomous_paper_quality.sh` | End-to-end deterministic demo |

---

## Task 1: Implement `TradingQualityThresholdPolicy` and result models

**Files:**
- Create: `src/atlas_agent/agent/autonomous_paper_quality.py`
- Test: `tests/test_autonomous_paper_quality.py`

- [ ] **Step 1: Write the failing test**

```python
from atlas_agent.agent.autonomous_paper_quality import TradingQualityThresholdPolicy


def test_default_threshold_policy_is_conservative():
    policy = TradingQualityThresholdPolicy()
    assert policy.min_bars_processed == 10
    assert policy.min_fills == 1
    assert policy.min_no_trade_decisions == 1
    assert policy.min_risk_rejections == 1
    assert policy.max_drawdown_pct == 50.0
    assert policy.max_exposure_pct == 200.0
    assert policy.max_turnover == 100.0
    assert policy.max_cost_impact_pct == 10.0
    assert policy.min_data_coverage == 0.5
    assert policy.max_invalid_metric_count == 0
```

Run: `python3.11 -m pytest tests/test_autonomous_paper_quality.py::test_default_threshold_policy_is_conservative -v`
Expected: FAIL (module not found)

- [ ] **Step 2: Implement the policy model**

```python
from __future__ import annotations

from dataclasses import dataclass, field
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
    def from_dict(cls, data: dict[str, Any]) -> "TradingQualityThresholdPolicy":
        return cls(**{k: data[k] for k in cls.to_dict(TradingQualityThresholdPolicy()) if k in data})
```

Run: `python3.11 -m pytest tests/test_autonomous_paper_quality.py::test_default_threshold_policy_is_conservative -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/atlas_agent/agent/autonomous_paper_quality.py tests/test_autonomous_paper_quality.py
git commit -m "feat(cand-004): add TradingQualityThresholdPolicy"
```

---

## Task 2: Implement artifact loading and integrity checks

**Files:**
- Modify: `src/atlas_agent/agent/autonomous_paper_quality.py`
- Test: `tests/test_autonomous_paper_quality.py`

- [ ] **Step 1: Write the failing test**

```python
import json
from pathlib import Path

from atlas_agent.agent.autonomous_paper_quality import (
    _load_artifacts,
    build_trading_quality_gate,
)


def test_missing_metrics_fail_closed(tmp_path: Path):
    result = build_trading_quality_gate(
        metrics_path=str(tmp_path / "missing.json"),
        decisions_path=str(tmp_path / "missing.jsonl"),
        fills_path=str(tmp_path / "missing.jsonl"),
    )
    assert result["quality_state"] == "not_evaluated"
    assert any("metrics" in e.lower() for e in result["blockers"])
```

Run: `python3.11 -m pytest tests/test_autonomous_paper_quality.py::test_missing_metrics_fail_closed -v`
Expected: FAIL

- [ ] **Step 2: Implement artifact loading helpers**

Add to `autonomous_paper_quality.py`:

```python
import json
import math
from pathlib import Path
from typing import Any

from atlas_agent.agent.autonomous_paper_metrics import calculate_stateful_paper_metrics
from atlas_agent.agent.autonomous_paper_models import StatefulPaperMetrics, StatefulPaperState


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
```

- [ ] **Step 3: Implement `build_trading_quality_gate` skeleton**

```python
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


def _dimension(name: str, passed: bool, score: float, reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "score": float(max(0.0, min(1.0, score))),
        "reason": reason,
    }


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

    # Placeholder for dimension evaluation; filled in Task 3.
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
```

Run: `python3.11 -m pytest tests/test_autonomous_paper_quality.py::test_missing_metrics_fail_closed -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/atlas_agent/agent/autonomous_paper_quality.py tests/test_autonomous_paper_quality.py
git commit -m "feat(cand-004): add artifact loading and gate skeleton"
```

---

## Task 3: Implement dimension evaluation

**Files:**
- Modify: `src/atlas_agent/agent/autonomous_paper_quality.py`
- Test: `tests/test_autonomous_paper_quality.py`

- [ ] **Step 1: Add helper functions**

Add below `_load_artifacts`:

```python
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
```

- [ ] **Step 2: Implement `_evaluate_dimensions`**

```python
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
    executed_count = decision_counts.get("paper_executed", 0)
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
    cost_impact_pct = (
        (total_commission + total_slippage) / ending_equity * 100.0
        if ending_equity > 0
        else 0.0
    )

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
    state_ok = False
    state_reason = "No state artifact provided."
    if state:
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
    cost_ok = total_commission >= 0 and total_slippage >= 0
    dimensions.append(_dimension(
        "cost_accounting",
        cost_ok,
        1.0 if cost_ok else 0.0,
        f"Commission={total_commission}, slippage={total_slippage}.",
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
    if consistency:
        consistency_ok = consistency.get("consistent", False)
        dimensions.append(_dimension(
            "replay_or_recompute_consistency",
            consistency_ok,
            1.0 if consistency_ok else 0.0,
            consistency.get("reason", "Consistency evaluated."),
        ))
    else:
        dimensions.append(_dimension(
            "replay_or_recompute_consistency",
            False,
            0.0,
            "Metric recomputation unavailable.",
        ))

    # data_coverage
    data_ok = bars_processed >= policy.min_bars_processed
    coverage_reason = f"Bars processed: {bars_processed} (required >= {policy.min_bars_processed})."
    dimensions.append(_dimension("data_coverage", data_ok, 1.0 if data_ok else 0.0, coverage_reason))

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
```

- [ ] **Step 3: Update `build_trading_quality_gate` to use `_evaluate_dimensions`**

Replace the placeholder return with:

```python
    dimensions = _evaluate_dimensions(
        metrics=metrics,
        decisions=decisions,
        fills=fills,
        state=state,
        scorecard=scorecard,
        policy=policy,
        benchmark=None,
        consistency=None,
    )

    # Determine quality state
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
        "symbol": metrics.get("data_source_redacted"),
        "quality_state": quality_state,
        "blockers": blockers,
        "dimensions": dimensions,
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
```

- [ ] **Step 4: Add dimension tests**

```python
def test_no_fills_blocked(tmp_path: Path):
    metrics = {
        "run_id": "r1",
        "starting_cash": 10000.0,
        "ending_cash": 10000.0,
        "ending_equity": 10000.0,
        "total_return_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "number_of_trades": 0,
        "number_of_fills": 0,
        "number_of_rejections": 1,
        "gross_exposure": 0.0,
        "net_exposure": 0.0,
        "total_commission": 0.0,
        "total_slippage": 0.0,
        "bars_processed": 10,
        "data_source_redacted": "demo.csv",
        "generated_at": "2026-01-01T00:00:00Z",
    }
    _write_artifacts(tmp_path, metrics, [], [])
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
    )
    assert result["quality_state"] in ("blocked", "paper_activity_observed")
    trade_dim = next(d for d in result["dimensions"] if d["name"] == "trade_activity")
    assert not trade_dim["passed"]
```

Add helper `_write_artifacts` in the test file:

```python
def _write_artifacts(tmp_path: Path, metrics: dict, decisions: list, fills: list):
    (tmp_path / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    (tmp_path / "decisions.jsonl").write_text(
        "\n".join(json.dumps(d) for d in decisions), encoding="utf-8"
    )
    (tmp_path / "fills.jsonl").write_text(
        "\n".join(json.dumps(f) for f in fills), encoding="utf-8"
    )
```

Run focused tests to ensure no crashes:

```bash
python3.11 -m pytest tests/test_autonomous_paper_quality.py -v
```

Expected: all current tests pass or fail as expected.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_agent/agent/autonomous_paper_quality.py tests/test_autonomous_paper_quality.py
git commit -m "feat(cand-004): add quality gate dimensions"
```

---

## Task 4: Implement benchmark comparison and metric recomputation

**Files:**
- Modify: `src/atlas_agent/agent/autonomous_paper_quality.py`
- Test: `tests/test_autonomous_paper_quality.py`

- [ ] **Step 1: Implement `_compute_benchmark`**

```python
from atlas_agent.data.market_data import load_market_data


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

    # Determine evaluated window from decisions if present.
    if decisions:
        first_idx = min((d.get("bar_index", 0) for d in decisions if isinstance(d.get("bar_index"), int)), default=0)
        last_idx = max((d.get("bar_index", 0) for d in decisions if isinstance(d.get("bar_index"), int)), default=len(bars) - 1)
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

    start_price = float(bars[first_idx].get("close", bars[first_idx].close))
    end_price = float(bars[last_idx].get("close", bars[last_idx].close))
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
```

- [ ] **Step 2: Implement `_recompute_and_compare_metrics`**

```python
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

    try:
        fill_history = [BacktestFill(**f) for f in fills]
    except Exception as exc:
        return {
            "consistent": False,
            "reason": f"Could not parse fills: {exc}",
            "recomputed": None,
        }

    starting_cash = _safe_float(metrics.get("starting_cash"), 1.0)
    cash = _safe_float(metrics.get("ending_cash"), starting_cash)
    bars_processed = int(metrics.get("bars_processed", 0))
    current_price = _safe_float(metrics.get("ending_cash"), starting_cash) / starting_cash  # fallback

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

    # Derive current price from the last fill if no position.
    if fill_history:
        current_price = float(fill_history[-1].price)

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
        if diff > tolerance and diff / max(abs(provided), 1.0) > tolerance:
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
```

- [ ] **Step 3: Wire benchmark and consistency into `build_trading_quality_gate`**

Before calling `_evaluate_dimensions`, add:

```python
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
```

Then include `benchmark=benchmark` and `consistency=consistency` in `_evaluate_dimensions`.

- [ ] **Step 4: Add tests**

```python
def test_benchmark_unavailable_without_data_path(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    _write_artifacts(tmp_path, metrics, decisions, fills)
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
    )
    assert result["benchmark"]["available"] is False


def test_invalid_nan_metric_blocks(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    metrics["total_return_pct"] = float("nan")
    _write_artifacts(tmp_path, metrics, decisions, fills)
    result = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
    )
    assert result["quality_state"] == "blocked"
    metric_dim = next(d for d in result["dimensions"] if d["name"] == "metric_validity")
    assert not metric_dim["passed"]
```

- [ ] **Step 5: Commit**

```bash
git add src/atlas_agent/agent/autonomous_paper_quality.py tests/test_autonomous_paper_quality.py
git commit -m "feat(cand-004): add benchmark and metric recomputation"
```

---

## Task 5: Implement artifact writers

**Files:**
- Modify: `src/atlas_agent/agent/autonomous_paper_quality.py`
- Test: `tests/test_autonomous_paper_quality.py`

- [ ] **Step 1: Implement `write_trading_quality_artifacts`**

```python
def _redact_path(path: str | Path | None) -> str | None:
    if path is None:
        return None
    p = Path(path)
    try:
        # Relativize against cwd if possible; otherwise use basename.
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
```

- [ ] **Step 2: Add writer test**

```python
def test_artifacts_written(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    _write_artifacts(tmp_path, metrics, decisions, fills)
    report = build_trading_quality_gate(
        metrics_path=tmp_path / "metrics.json",
        decisions_path=tmp_path / "decisions.jsonl",
        fills_path=tmp_path / "fills.jsonl",
    )
    json_path, md_path = write_trading_quality_artifacts(report, tmp_path / "out")
    assert json_path.exists()
    assert md_path.exists()
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["quality_state"] == report["quality_state"]
    assert "Disclaimer" in md_path.read_text(encoding="utf-8")
```

- [ ] **Step 3: Commit**

```bash
git add src/atlas_agent/agent/autonomous_paper_quality.py tests/test_autonomous_paper_quality.py
git commit -m "feat(cand-004): add quality gate artifact writers"
```

---

## Task 6: Add CLI command

**Files:**
- Modify: `src/atlas_agent/cli.py`
- Modify: `tests/fixtures/cli_command_contract.json`
- Test: `tests/test_autonomous_paper_quality.py`

- [ ] **Step 1: Register parser**

In `build_parser()` after the `autonomous-scorecard` block (around line 900), add:

```python
    agent_autonomous_quality = agent_sub.add_parser(
        "autonomous-paper-quality",
        help="Evaluate stateful autonomous-paper trading behavior against a quality gate (paper-only, offline).",
    )
    agent_autonomous_quality.add_argument("--metrics", required=True, help="Path to metrics.json")
    agent_autonomous_quality.add_argument("--decisions", required=True, help="Path to decisions.jsonl")
    agent_autonomous_quality.add_argument("--fills", required=True, help="Path to fills.jsonl")
    agent_autonomous_quality.add_argument("--state", help="Path to state.json (optional)")
    agent_autonomous_quality.add_argument("--scorecard", help="Path to autonomous-paper-scorecard.json (optional)")
    agent_autonomous_quality.add_argument("--threshold-policy", help="Path to threshold policy JSON (optional)")
    agent_autonomous_quality.add_argument("--data-path", help="Path to OHLCV CSV for benchmark comparison (optional)")
    agent_autonomous_quality.add_argument("--output-dir", help="Directory for trading-quality-gate.json and trading-quality-report.md")
    agent_autonomous_quality.add_argument("--json", action="store_true", help="Emit result as JSON")
```

- [ ] **Step 2: Add dispatch branch**

In `main()` under the `agent` command block, after `autonomous-scorecard` handling, add:

```python
            elif args.agent_command == "autonomous-paper-quality":
                from atlas_agent.agent.autonomous_paper_quality import (
                    TradingQualityThresholdPolicy,
                    build_trading_quality_gate,
                    write_trading_quality_artifacts,
                )

                policy = TradingQualityThresholdPolicy()
                if getattr(args, "threshold_policy", None):
                    policy_data = json.loads(Path(args.threshold_policy).read_text(encoding="utf-8"))
                    policy = TradingQualityThresholdPolicy.from_dict(policy_data)

                output_dir = getattr(args, "output_dir", None) or str(
                    config.reports_dir / "autonomous_paper_quality"
                )
                report = build_trading_quality_gate(
                    metrics_path=args.metrics,
                    decisions_path=args.decisions,
                    fills_path=args.fills,
                    state_path=getattr(args, "state", None),
                    scorecard_path=getattr(args, "scorecard", None),
                    data_path=getattr(args, "data_path", None),
                    policy=policy,
                )
                json_path, md_path = write_trading_quality_artifacts(report, output_dir)

                if getattr(args, "json", False):
                    return emit_cli_success(
                        "atlas agent autonomous-paper-quality",
                        {"report": report, "json_path": str(json_path), "md_path": str(md_path)},
                    )

                print(f"trading-quality-gate: {report['quality_state']}")
                print(f"  json: {json_path}")
                print(f"  md:   {md_path}")
                if report["blockers"]:
                    print("  blockers:")
                    for blocker in report["blockers"]:
                        print(f"    - {blocker}")
                return 0 if report["quality_state"] in (
                    "paper_quality_reviewable",
                    "eligible_for_shadow_live_quality_review",
                ) else 2
```

- [ ] **Step 3: Update CLI contract fixture**

Add `"autonomous-paper-quality"` to the `agent` subcommands list in `tests/fixtures/cli_command_contract.json`.

- [ ] **Step 4: Add CLI smoke test**

```python
import subprocess


def test_cli_autonomous_paper_quality_smoke(tmp_path: Path):
    metrics, decisions, fills = _minimal_valid_fixtures()
    _write_artifacts(tmp_path, metrics, decisions, fills)
    out_dir = tmp_path / "out"
    result = subprocess.run(
        [
            "python3.11", "-m", "atlas_agent.cli",
            "agent", "autonomous-paper-quality",
            "--metrics", str(tmp_path / "metrics.json"),
            "--decisions", str(tmp_path / "decisions.jsonl"),
            "--fills", str(tmp_path / "fills.jsonl"),
            "--output-dir", str(out_dir),
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode in (0, 2), result.stderr
    assert (out_dir / "trading-quality-gate.json").exists()
```

- [ ] **Step 5: Commit**

```bash
git add src/atlas_agent/cli.py tests/fixtures/cli_command_contract.json tests/test_autonomous_paper_quality.py
git commit -m "feat(cand-004): add autonomous-paper-quality CLI"
```

---

## Task 7: Add contract checker

**Files:**
- Create: `scripts/check_autonomous_paper_quality_contract.py`
- Create: `tests/test_autonomous_paper_quality_contract.py`

Copy and adapt the CAND-002 scorecard checker pattern. Key differences:

- `DOC = "docs/autonomous-paper-quality-gate.md"`
- `MODULES = ["src/atlas_agent/agent/autonomous_paper_quality.py"]`
- `TEST_MODULE = "tests/test_autonomous_paper_quality.py"`
- `CONTRACT_TEST_MODULE = "tests/test_autonomous_paper_quality_contract.py"`
- `CLI_COMMAND = '"autonomous-paper-quality"'`
- `REQUIRED_DOC_PHRASES`: add `"paper-only"`, `"no live trading"`, `"RiskManager"`, `"not financial advice"`, `"does **not** claim autonomous live trading readiness"`, `"shadow-live"`
- `FORBIDDEN_DOC_PHRASES`: same as CAND-002
- Forbidden imports: brokers, providers, execution.live, credential loading, place_order, live_trading_enabled_true, etc.

- [ ] **Step 1: Write checker**

Use `scripts/check_autonomous_paper_scorecard_contract.py` as the template. Replace module names and add `REQUIRED_QUALITY_STATES` and `REQUIRED_DIMENSIONS` checks that verify the literal tuples `QUALITY_STATES` and `DIMENSIONS` contain the expected values.

- [ ] **Step 2: Write checker tests**

Copy `tests/test_autonomous_paper_scorecard_contract.py` and adapt:

- `test_checker_passes_on_real_repo`
- `test_checker_json_output`
- `test_checker_fails_when_forbidden_phrase_present`
- `test_checker_fails_on_forbidden_import`
- `test_checker_imports_no_network_or_credentials`

- [ ] **Step 3: Commit**

```bash
git add scripts/check_autonomous_paper_quality_contract.py tests/test_autonomous_paper_quality_contract.py
git commit -m "feat(cand-004): add quality gate contract checker"
```

---

## Task 8: Wire checkers into dev/release scripts

**Files:**
- Modify: `scripts/dev_check.sh`
- Modify: `scripts/release_check.sh`

- [ ] **Step 1: Add to `dev_check.sh`**

After the CAND-002 scorecard pytest block (around `4p`), add:

```bash
echo ""
echo "4q. autonomous paper quality gate contract check"
SECONDS=0
"$PYTHON_BIN" scripts/check_autonomous_paper_quality_contract.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))

echo ""
echo "4r. autonomous paper quality gate tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_autonomous_paper_quality.py tests/test_autonomous_paper_quality_contract.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
```

- [ ] **Step 2: Add to `release_check.sh`**

Mirror the same blocks in the release check script at the equivalent numbered section.

- [ ] **Step 3: Commit**

```bash
git add scripts/dev_check.sh scripts/release_check.sh
git commit -m "feat(cand-004): wire quality gate checker into dev/release checks"
```

---

## Task 9: Add docs and release metadata

**Files:**
- Create: `docs/autonomous-paper-quality-gate.md`
- Modify: `docs/releases/v0.6.16-candidates.json`
- Modify: `docs/releases/v0.6.16-candidates.md`
- Modify: `docs/releases/v0.6.16-candidate-selection.md`
- Modify: `docs/releases/v0.6.16-plan.md`
- Modify: `docs/bounded-live-autonomy-governance.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write user-facing doc**

`docs/autonomous-paper-quality-gate.md` should include:

- Status banner: `paper-only`, `not financial advice`
- One-paragraph scope
- Explicit `does **not** claim autonomous live trading readiness`
- Safety boundaries table
- CLI usage
- Artifact output description
- Cross-references to `bounded-live-autonomy-governance.md` and `shadow-live-readiness-contract.md`
- Reviewer checklist

- [ ] **Step 2: Update release metadata**

Add CAND-004 as `implemented` in the JSON and human-readable candidate docs. Keep CAND-001/002/003 as implemented.

- [ ] **Step 3: Update bounded autonomy governance**

Add a truth line like:

> CAND-004 (v0.6.16): A trading-quality gate evaluates stateful paper behavior only; it does not approve live trading.

- [ ] **Step 4: Update CHANGELOG**

Under `## [Unreleased] > ### Added` add bullet points for the new module, CLI, checker, tests, and docs. Under `### Safety` reiterate no live trading, no broker calls, no credential loading.

- [ ] **Step 5: Commit**

```bash
git add docs/autonomous-paper-quality-gate.md docs/releases/ docs/bounded-live-autonomy-governance.md CHANGELOG.md
git commit -m "docs(cand-004): add quality gate docs and release metadata"
```

---

## Task 10: Add demo script

**Files:**
- Create: `scripts/demo_autonomous_paper_quality.sh`

- [ ] **Step 1: Create deterministic demo**

The demo should:

1. Run `bash scripts/demo_autonomous_paper_stateful.sh` or call the stateful runner directly to generate artifacts.
2. Run `atlas agent autonomous-paper-quality --metrics ... --decisions ... --fills ... --state ... --output-dir ...`.
3. Print the final quality state and key metrics.
4. Exit non-zero if quality state is `not_evaluated` or `blocked`.

- [ ] **Step 2: Commit**

```bash
git add scripts/demo_autonomous_paper_quality.sh
git commit -m "demo(cand-004): add trading quality gate demo"
```

---

## Task 11: Verification

Run these commands in order. Do not weaken checks to pass.

- [ ] `git status`
- [ ] `git diff --check`
- [ ] `python3.11 -m compileall src`
- [ ] `python3.11 -m pytest tests/test_autonomous_paper_quality.py tests/test_autonomous_paper_quality_contract.py -q`
- [ ] `python3.11 -m pytest tests/test_autonomous_paper_loop.py tests/test_autonomous_paper_loop_contract.py tests/test_shadow_live_contract.py tests/test_autonomous_paper_scorecard.py tests/test_autonomous_paper_scorecard_contract.py tests/test_autonomous_paper_runner.py tests/test_autonomous_paper_lock.py -q`
- [ ] `python3.11 scripts/check_autonomous_paper_quality_contract.py --json`
- [ ] `python3.11 scripts/check_autonomous_paper_loop_contract.py`
- [ ] `python3.11 scripts/check_autonomous_paper_scorecard_contract.py`
- [ ] `python3.11 scripts/check_shadow_live_contract.py`
- [ ] `python3.11 scripts/check_forbidden_claims.py`
- [ ] `python3.11 scripts/check_cli_command_compatibility.py`
- [ ] `python3.11 scripts/check_release_metadata.py`
- [ ] `python3.11 scripts/check_version_consistency.py`
- [ ] `python3.11 scripts/check_bounded_autonomy_governance.py`
- [ ] `python3.11 -m pip check`
- [ ] `bash scripts/demo_autonomous_paper_stateful.sh`
- [ ] `bash scripts/demo_autonomous_paper_quality.sh`
- [ ] `atlas validate`
- [ ] `atlas agent autonomous-paper --help`
- [ ] `atlas agent autonomous-paper-quality --help`
- [ ] `atlas run --mode paper`
- [ ] `atlas run --mode live` (must fail safely)
- [ ] `./scripts/release_check.sh --quick`

If all pass, commit any final fixes and push:

```bash
git push origin main
```

with message `feat(cand-004): add stateful paper trading quality gate`.
