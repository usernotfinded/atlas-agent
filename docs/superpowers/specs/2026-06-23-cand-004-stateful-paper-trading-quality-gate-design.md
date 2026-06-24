# CAND-004: Stateful Paper Trading Quality Gate — Design Spec

**Status:** Approved for implementation  
**Candidate:** CAND-004  
**Scope:** Paper-only, offline, deterministic evaluation of stateful autonomous paper trading behavior.

## Goal

Convert Atlas from “stateful autonomous paper plumbing works” into “stateful autonomous paper runs can be evaluated with meaningful trading-quality gates.”

CAND-004 measures **trading behavior**, not artifact hygiene and not live readiness. It answers:

> “Did the stateful autonomous paper run produce trading behavior that is coherent, bounded, risk-aware, and worth reviewing for future shadow-live/read-only comparison?”

It explicitly does **not** answer:

- “Is this profitable?”
- “Is this live-ready?”
- “Is this safe for autonomous real-money trading?”

## Architecture

Approach A: separate standalone quality gate.

- `src/atlas_agent/agent/autonomous_paper_quality.py` — single focused module.
- `atlas agent autonomous-paper-quality` — new CLI command.
- `scripts/check_autonomous_paper_quality_contract.py` — static contract checker.
- CAND-002 scorecard remains untouched; CAND-004 may optionally consume its JSON output as a cross-reference.

## Module Design

### `TradingQualityThresholdPolicy`

Typed model (dataclass/Pydantic) with conservative, test/demo-appropriate defaults.

| Threshold | Default | Purpose |
|-----------|---------|---------|
| `min_bars_processed` | `10` | Enough data to observe behavior |
| `min_fills` | `1` | At least one simulated fill |
| `min_no_trade_decisions` | `1` | At least one hold/no-trade decision |
| `min_risk_rejections` | `1` | At least one observed risk rejection |
| `max_drawdown_pct` | `50.0` | Hard drawdown bound |
| `max_exposure_pct` | `200.0` | Hard exposure bound |
| `max_turnover` | `100.0` | Hard turnover bound |
| `max_cost_impact_pct` | `10.0` | Combined commission + slippage vs equity |
| `min_data_coverage` | `0.5` | Fraction of expected bars present |
| `max_invalid_metric_count` | `0` | Zero tolerance for NaN/inf/missing metrics |

Defaults are intentionally loose for tests/demo. They do **not** require profitability.

### `build_trading_quality_gate(...)`

Primary entry point. Inputs:

- `metrics_path` (required)
- `decisions_path` (required)
- `fills_path` (required)
- `state_path` (optional)
- `scorecard_path` (optional)
- `policy` (optional, defaults to `TradingQualityThresholdPolicy()`)
- `data_path` (optional, for benchmark)

Steps:

1. Load and validate input artifact presence and JSON schema.
2. Compute coverage counts from decisions/fills.
3. Compute benchmark comparison from state/decisions or data file if available.
4. Recompute metrics from fills/state via `calculate_stateful_paper_metrics` and compare to provided metrics.
5. Evaluate each dimension with fail-closed logic.
6. Compute final quality state.
7. Return a portable, redacted result dict.

### Quality Dimensions

All dimensions produce `{"name", "passed": bool, "score": float, "reason": str}`.

| Dimension | Evaluates |
|-----------|-----------|
| `artifact_integrity` | Required files parse, required fields present |
| `stateful_resume_integrity` | State/checkpoint schema valid, cursor sane, identity preserved |
| `trade_activity` | Fill count ≥ `min_fills` |
| `risk_rejection_coverage` | Rejection count ≥ `min_risk_rejections` |
| `no_trade_coverage` | No-trade decisions ≥ `min_no_trade_decisions` |
| `cost_accounting` | Commission/slippage present and non-negative |
| `drawdown_bounds` | `max_drawdown_pct` ≤ threshold |
| `return_bounds` | Return finite, within ±100% default guard |
| `exposure_bounds` | Gross/net exposure ≤ threshold |
| `turnover_bounds` | Turnover ≤ threshold |
| `benchmark_comparison` | Buy-and-hold benchmark computed if data available |
| `replay_or_recompute_consistency` | Recomputed metrics match provided metrics within tolerance |
| `data_coverage` | Bars processed ≥ `min_bars_processed` and coverage ≥ `min_data_coverage` |
| `metric_validity` | No NaN/inf/missing metrics; invalid count ≤ threshold |
| `no_live_side_effects` | Scans text for live broker/provider/execution keywords and secret-like patterns |

### Quality States

Final `quality_state` is one of:

- `not_evaluated` — missing/unreadable inputs
- `blocked` — any critical dimension failed or metrics invalid
- `paper_activity_observed` — activity exists but insufficient quality for review
- `paper_quality_reviewable` — all thresholds pass, metrics valid, but not promoted
- `eligible_for_shadow_live_quality_review` — conservative superset pass; still not live-ready

### `_recompute_and_compare_metrics(...)`

- Recompute from `fills.jsonl` and `state.json` via existing `calculate_stateful_paper_metrics`.
- Compare total return, max drawdown, trade count, fill count, commission, slippage.
- Use small relative tolerance (e.g., 1e-6) and absolute tolerance for currency values.
- Fail closed on material mismatch.
- If recomputation is unavailable, record reason and block only if policy requires it.

### Benchmark Comparison

- Deterministic buy-and-hold using the same symbol and window if `data_path` or OHLCV window can be recovered.
- Output: `strategy_total_return_pct`, `benchmark_total_return_pct`, `excess_return_pct`.
- If unavailable, output `unavailable: true` and `reason`.
- Not required by default.

### Artifact Writers

`write_trading_quality_artifacts(report, output_dir)` writes:

- `trading-quality-gate.json`
- `trading-quality-report.md`

Both include:

- run identifiers
- input artifact references (relative/redacted)
- threshold policy
- metrics snapshot
- benchmark comparison
- dimension results
- quality state
- blocked reasons
- unavailable metric reasons
- explicit paper-only / not-live-ready disclaimer

## CLI Design

```bash
atlas agent autonomous-paper-quality \
  --metrics reports/autonomous_paper/<run>-metrics.json \
  --decisions reports/autonomous_paper/<run>-decisions.jsonl \
  --fills reports/autonomous_paper/<run>-fills.jsonl \
  --state reports/autonomous_paper_state/<run>-state.json \
  [--scorecard reports/autonomous_paper_scorecard/autonomous-paper-scorecard.json] \
  [--threshold-policy policy.json] \
  [--output-dir reports/autonomous_paper_quality] \
  [--json]
```

- Offline-only, deterministic, read-only w.r.t. runner state.
- Exit codes: `0` for `paper_quality_reviewable` or `eligible_for_shadow_live_quality_review`, `2` for `blocked`/`not_evaluated`/`paper_activity_observed`.

## Safety Boundaries

- No broker/provider/live execution imports.
- No credential loading.
- No live order submission.
- No shadow-live implementation.
- No claims of profitability, live readiness, or guaranteed outcomes.
- All behavior deterministic and local-only.

## Test Plan

- Valid quality gate generation
- Missing metrics fail-closed
- Malformed metrics fail-closed
- No fills blocked/downgraded
- Risk-rejection absence handled per policy
- No no-trade decisions blocked/downgraded
- Drawdown above threshold blocks
- Exposure above threshold blocks
- Turnover above threshold blocks
- Invalid/NaN/inf metrics block
- Benchmark unavailable behavior
- Benchmark comparison computed correctly
- Threshold policy serialized
- JSON/Markdown artifacts written
- CLI smoke behavior
- No broker/provider/live import or credential usage
- Absolute paths redacted from output artifacts

## Files to Create/Modify

**Create:**

- `src/atlas_agent/agent/autonomous_paper_quality.py`
- `scripts/check_autonomous_paper_quality_contract.py`
- `tests/test_autonomous_paper_quality.py`
- `tests/test_autonomous_paper_quality_contract.py`
- `docs/autonomous-paper-quality-gate.md`
- `docs/superpowers/plans/2026-06-23-cand-004-stateful-paper-trading-quality-gate.md`
- `scripts/demo_autonomous_paper_quality.sh`

**Modify:**

- `src/atlas_agent/cli.py` — register command
- `tests/fixtures/cli_command_contract.json` — add subcommand
- `docs/releases/v0.6.16-candidates.json`
- `docs/releases/v0.6.16-candidates.md`
- `docs/releases/v0.6.16-candidate-selection.md`
- `docs/releases/v0.6.16-plan.md`
- `docs/bounded-live-autonomy-governance.md`
- `CHANGELOG.md`
- `scripts/dev_check.sh`
- `scripts/release_check.sh`

## Verification Checklist

- `git status`
- `git diff --check`
- `python3.11 -m compileall src`
- `python3.11 -m pytest tests/test_autonomous_paper_quality.py tests/test_autonomous_paper_quality_contract.py -q`
- CAND-001/002/003 regression tests
- All contract checkers
- `atlas validate`
- `atlas agent autonomous-paper --help`
- `atlas agent autonomous-paper-quality --help`
- `atlas run --mode paper`
- `atlas run --mode live` remains fail-closed
- `./scripts/release_check.sh --quick`
