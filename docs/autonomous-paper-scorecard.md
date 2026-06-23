# Autonomous Paper Decision Quality Scorecard and Promotion Gate

> **Status:** planning-only. This document describes a paper-quality evaluation
> gate, not a live-trading feature. It does **not** authorize autonomous live
> trading, live order submission, or shadow-live execution.
>
> **Not financial advice.** Atlas Agent is a software tool, not a financial
> advisor. Trading involves significant risk of loss. Past performance does not
> guarantee future results.
>
> This document does **not** claim autonomous live trading readiness.

## What this is

The autonomous paper scorecard is a deterministic, offline evaluation layer for
artifacts produced by `atlas agent autonomous-paper`. It reads the local
`decisions.jsonl` and `manifest.json` files and answers one question only:

> "Is the autonomous-paper loop producing decision artifacts good enough to be
> considered for future shadow-live/read-only evaluation?"

It must **not** be read as:

> "Is this ready for autonomous live trading?"

## What this is not

- It is **not** a live trading system.
- It does **not** enable live submit, broker order submission, or real provider
  execution.
- It does **not** load broker credentials, API keys, or other secrets.
- It does **not** mutate runtime configuration to live mode.
- It does **not** guarantee profit, safety, or eliminated risk.

## Safety boundaries

| Boundary | How it is preserved |
|---|---|
| **Paper-only** | The scorecard reads artifacts only; all decisions and the manifest must declare `mode == "paper"`. |
| **No live trading** | The scorecard rejects artifacts that reference live trading, live broker submit, or provider execution. |
| **No broker order submission** | The scorecard module imports no broker code and never calls `broker.submit` or equivalent. |
| **No provider execution** | The scorecard imports no provider code and makes no network or LLM calls. |
| **No credentials** | The scorecard does not read API keys, tokens, or passwords, and it flags secret-like strings in artifacts as audit failures. |
| **Fail-closed promotion** | The default promotion state is `blocked` unless required evidence exists. |
| **Deterministic** | The scorecard is local-first, uses no randomness, and produces the same result for the same inputs. |

## CLI usage

```bash
# Run the autonomous paper loop and emit evidence
atlas agent autonomous-paper \
  --symbol DEMO-SYMBOL \
  --data-path data/sample/ohlcv.csv \
  --max-cycles 5 \
  --evidence-dir reports/autonomous_paper_evidence

# Evaluate the evidence with the scorecard
atlas agent autonomous-scorecard \
  --decisions reports/autonomous_paper_evidence/<run_id>/decisions.jsonl \
  --manifest reports/autonomous_paper_evidence/<run_id>/manifest.json \
  --output-dir reports/autonomous_paper_scorecard
```

Optional arguments:

- `--replay-decisions PATH` — compare a second decisions file to verify replay
  determinism.
- `--output-dir DIR` — directory for `autonomous-paper-scorecard.json` and
  `autonomous-paper-scorecard.md`.
- `--json` — emit the scorecard dict as JSON on stdout.

## Scorecard dimensions

| Dimension | Passing criteria |
|---|---|
| `schema_validity` | `decisions.jsonl` parses and contains required fields; `manifest.json` contains required fields. |
| `replay_determinism` | All decisions share the same `run_id`; iterations are sequential; timestamps are monotonic; decision counts match the manifest. If `--replay-decisions` is provided, the replay must match per-iteration state and action. |
| `risk_gate_compliance` | `paper_executed` decisions have `risk_result.allowed == true`; `risk_blocked` decisions have `allowed == false`. This confirms the paper loop routed every proposed order through `RiskManager` and recorded the gate result. |
| `kill_switch_compliance` | If a kill-switch violation is present, no `paper_executed` decisions exist. |
| `no_live_side_effects` | All artifacts report `mode == "paper"` and contain no live broker/provider references. |
| `audit_redaction` | Artifact text contains no secret-like patterns (`api_key`, `token`, `password`, etc.). |
| `decision_coverage` | At least one decision exists and the manifest count matches the actual row count. |
| `blocked_reason_quality` | Every `risk_blocked` decision has a non-empty `blocked_reason` and risk violations. |
| `no_trade_reason_quality` | Every `no_trade` decision has `proposed_action == "hold"`, no proposed order, and `risk_result.status == "not_applicable"`. |
| `artifact_completeness` | Both required files exist, are non-empty, and the manifest references them. |
| `future_shadow_live_prerequisites` | The run completed; demonstrated at least one `paper_executed`, one `no_trade`, and one `risk_blocked` decision; all safety dimensions pass. |

## Promotion states

- `not_evaluated` — required artifact paths are missing or unreadable.
- `blocked` — a critical dimension failed or the run is not suitable for further
  review.
- `paper_quality_observed` — artifacts are valid and the run is well-formed, but
  does not yet meet the conservative shadow-live review prerequisites.
- `eligible_for_shadow_live_review` — all required dimensions pass and the run
  demonstrates the diversity required before any future shadow-live/read-only
  evaluation.

`eligible_for_shadow_live_review` is **not** live readiness. It only means the
paper artifact meets conservative offline criteria for a future human-reviewed
shadow-live comparison stage.

## Artifacts

- `src/atlas_agent/agent/autonomous_paper_scorecard.py` — scorecard builder and
  Markdown renderer.
- `scripts/check_autonomous_paper_scorecard_contract.py` — static contract
  checker.
- `tests/test_autonomous_paper_scorecard.py` — scorecard tests.
- `tests/test_autonomous_paper_scorecard_contract.py` — contract checker tests.
- `scripts/demo_autonomous_paper_scorecard.sh` — offline demo.

## Related documents

- [Autonomous Paper Loop](autonomous-paper-loop.md) — the decision loop that
  produces the artifacts evaluated here.
- [Shadow-Live Readiness Contract](shadow-live-readiness-contract.md) — the
  planning-only contract for any future shadow-live/read-only stage.
- [Bounded Live Autonomy Governance](bounded-live-autonomy-governance.md) — the
  governance model that keeps live trading gated and human-approved.
