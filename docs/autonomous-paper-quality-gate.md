# Autonomous Paper Trading Quality Gate

> **Status:** `paper-only`, `offline`, deterministic local evaluation.
> This document describes a paper-trading quality gate, not a live-trading
> feature. It does **not** authorize autonomous live trading, live order
> submission, or shadow-live execution. No live trading is enabled.
>
> **Not financial advice.** Atlas Agent is a software tool, not a financial
> advisor. Trading involves significant risk of loss. Past performance does not
> guarantee future results.
>
> This document does **not** claim autonomous live trading readiness and does
> **not** claim profitability.

## What this is

CAND-004 adds a deterministic, offline trading-quality gate that evaluates
stateful paper trading behavior produced by `atlas agent autonomous-paper` and
the CAND-003 execution-neutral trading kernel. It reads local metrics,
decisions, fills, and persisted runner-state artifacts and answers one question
only:

> "Does the stateful paper run exhibit enough trading quality and safety hygiene
> to be considered for a future shadow-live/read-only quality review?"

It must **not** be read as:

> "Is this ready for autonomous live trading?"

The gate is an additional evaluation layer on top of the CAND-002 scorecard:
while the scorecard inspects decision artifacts and process conformance, the
trading-quality gate inspects portfolio state, simulated fills, cost accounting,
drawdown behavior, exposure, turnover, benchmark comparison, replay consistency,
and metric validity.

## What this is not

- It is **not** a live trading system.
- It does **not** enable live submit, broker order submission, or real provider
  execution.
- It does **not** load broker credentials, API keys, or other secrets.
- It does **not** mutate runtime configuration to live mode.
- It does **not** guarantee profit, safety, or eliminated risk.
- It does **not** approve shadow-live execution; it only produces a reviewable
  quality state.

## Safety boundaries

| Boundary | How it is preserved |
|---|---|
| **No broker/provider/live execution calls** | The gate imports no broker or provider code, makes no network calls, and rejects artifacts that reference live execution. |
| **No credential loading** | The gate does not read API keys, tokens, passwords, or other secrets. |
| **No live order submission** | The gate never calls `broker.submit`, `place_order`, `OrderRouter`, or equivalent. |
| **No shadow-live implementation** | The gate evaluates paper artifacts only and does not mirror a live account or emit live orders. |
| **Deterministic and local-only** | The gate is local-first, uses no randomness, and produces the same result for the same inputs. |
| **Paper-only** | All evaluated artifacts must declare `mode == "paper"`; live-mode artifacts are rejected. |
| **RiskManager remains mandatory** | Proposed orders must show `RiskManager` gating and recorded risk results. |

## CLI usage

```bash
# Evaluate a stateful paper run with the trading-quality gate
atlas agent autonomous-paper-quality \
  --metrics reports/autonomous_paper/<run>-metrics.json \
  --decisions reports/autonomous_paper/<run>-decisions.jsonl \
  --fills reports/autonomous_paper/<run>-fills.jsonl \
  --state reports/autonomous_paper_state/<run>-state.json \
  [--scorecard reports/autonomous_paper_scorecard/autonomous-paper-scorecard.json] \
  [--threshold-policy policy.json] \
  [--data-path data/ohlcv.csv] \
  --output-dir reports/autonomous_paper_quality \
  [--json]
```

Optional arguments:

- `--metrics PATH` — trading metrics JSON produced by the stateful paper runner.
- `--decisions PATH` — decision log in `jsonl` format.
- `--fills PATH` — simulated fill log in JSON or `jsonl` format.
- `--state PATH` — persisted runner state JSON produced with `--state-dir`.
- `--scorecard PATH` — optional CAND-002 scorecard JSON to inherit promotion state.
- `--threshold-policy PATH` — optional JSON policy defining pass thresholds for
  drawdown, return, exposure, turnover, and benchmark comparison.
- `--data-path PATH` — optional OHLCV CSV used to verify data coverage.
- `--output-dir DIR` — directory for `trading-quality-gate.json` and
  `trading-quality-report.md`.
- `--json` — emit the gate result dict as JSON on stdout.

## Output artifacts

- `trading-quality-gate.json` — machine-readable gate result, quality state,
  per-dimension pass/fail flags, thresholds, and summary statistics.
- `trading-quality-report.md` — human-readable report with safety banner,
  quality state, dimension table, and reviewer notes.

## Quality states

- `not_evaluated` — required artifact paths are missing or unreadable.
- `blocked` — a critical dimension failed or the run is not suitable for further
  review.
- `paper_activity_observed` — the run produced some valid trading activity but
  does not yet meet reviewable quality thresholds.
- `paper_quality_reviewable` — artifacts are valid, metrics are plausible, and
  the run is suitable for a future shadow-live/read-only quality review.
- `eligible_for_shadow_live_quality_review` — all required dimensions pass, the
  run demonstrates conservative drawdown/return/exposure/turnover bounds, and
  the data coverage and replay consistency are satisfied.

`eligible_for_shadow_live_quality_review` is **not** live readiness. It only
means the paper run meets conservative offline criteria for a future
human-reviewed shadow-live/read-only comparison stage.

## Quality dimensions

| Dimension | Passing criteria |
|---|---|
| `artifact_integrity` | All required input files parse correctly, required fields are present, and the manifest or state references the correct artifact paths. |
| `stateful_resume_integrity` | The persisted state contains a deterministic `run_id`, the last processed bar index or timestamp, and no duplicate-bar markers are contradictory. |
| `trade_activity` | The run contains at least one executed paper trade and at least one `no_trade` or `risk_blocked` decision. |
| `risk_rejection_coverage` | At least one proposed order was blocked by `RiskManager` with a non-empty reason and recorded violations. |
| `no_trade_coverage` | At least one `no_trade` decision exists with `proposed_action == "hold"` and no proposed order. |
| `cost_accounting` | Metrics include commission and slippage costs; net returns are computed after costs. |
| `drawdown_bounds` | Maximum drawdown remains within the configured conservative threshold. |
| `return_bounds` | Returns are bounded and not inconsistent with the number of trades or bars. |
| `exposure_bounds` | Maximum position exposure remains within configured symbol and portfolio limits. |
| `turnover_bounds` | Annualized turnover remains within a configured conservative threshold. |
| `benchmark_comparison` | If a benchmark is configured, comparison metrics are present and computed deterministically from local data. |
| `replay_or_recompute_consistency` | Recomputing metrics from decisions and fills yields the same result, or replaying decisions reproduces the same state. |
| `data_coverage` | The number of processed bars matches the input data and the state resume marker. |
| `metric_validity` | Key metrics (sharpe, sortino, max drawdown, win rate, etc.) are finite, non-missing, and internally consistent. |
| `no_live_side_effects` | All artifacts report `mode == "paper"` and contain no live broker/provider references. |

## Cost impact approximation note

The `cost_impact_pct` metric produced by the trading-quality gate is an
approximation and a directional proxy for paper-run review. It is intended to
help reviewers quickly identify whether simulated commission and slippage costs
are materially affecting the run, not to provide high-precision production cost
analysis. Do not use it as a guarantee of live trading costs, profitability, or
execution quality.

## Artifacts

- `src/atlas_agent/agent/autonomous_paper_quality.py` — trading-quality gate
  builder and Markdown renderer.
- `scripts/check_autonomous_paper_quality_contract.py` — static contract
  checker.
- `tests/test_autonomous_paper_quality.py` — quality gate tests.
- `tests/test_autonomous_paper_quality_contract.py` — contract checker tests.

## Related documents

- [Bounded Live Autonomy Governance](bounded-live-autonomy-governance.md) — the
  governance model that keeps live trading gated and human-approved.
- [Shadow-Live Readiness Contract](shadow-live-readiness-contract.md) — the
  planning-only contract for any future shadow-live/read-only stage.
- [Autonomous Paper Decision Quality Scorecard and Promotion Gate](autonomous-paper-scorecard.md) — the CAND-002 scorecard that evaluates autonomous-paper artifacts for promotion eligibility.
- [Autonomous Paper Loop](autonomous-paper-loop.md) — the decision loop that
  produces the artifacts evaluated here.

## Reviewer checklist

- [ ] The gate rejects live-mode artifacts and artifacts with live broker/provider references.
- [ ] The gate never loads credentials, API keys, or other secrets.
- [ ] The gate never calls broker submit, provider execute, or order router methods.
- [ ] The gate imports no broker, provider, or live execution modules.
- [ ] All required quality states are defined in `autonomous_paper_quality.py` and tested.
- [ ] All required quality dimensions are defined in `autonomous_paper_quality.py` and tested.
- [ ] Default promotion state is `blocked` or `not_evaluated` when evidence is missing.
- [ ] CLI wiring in `cli.py` adds the `autonomous-paper-quality` subparser.
- [ ] The output artifacts include both JSON and Markdown reports.
- [ ] Documentation does not claim live trading readiness, profitability, or eliminated risk.
