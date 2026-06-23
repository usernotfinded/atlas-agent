# CAND-002: Autonomous Paper Decision Quality Scorecard and Promotion Gate

> **Status:** planning and design only. This document describes a proposed
> capability, not a shipped feature or a guarantee of future behavior.
>
> **Not financial advice.** Atlas Agent is a software tool, not a financial
> advisor. Trading involves risk of loss. Past performance does not guarantee
> future results.
>
> This document does **not** claim autonomous live trading readiness.

## Goal

Create a deterministic, offline-only scorecard that evaluates artifacts produced
by `atlas agent autonomous-paper`. The scorecard answers:

> "Is the autonomous-paper loop producing decision artifacts good enough to be
> considered for future shadow-live/read-only evaluation?"

It must **not** answer:

> "Is this ready for autonomous live trading?"

## Safety boundaries

- **Paper-only.** The scorecard reads local artifacts only; it does not execute
  trades, submit orders, or enable live trading.
- **No live submit.** The scorecard does not resolve a live execution broker,
  call `broker.place_order`, or set `can_submit`.
- **No provider calls.** The scorecard does not invoke LLM/provider APIs.
- **No credentials.** The scorecard does not read API keys, secrets, or broker
  credentials.
- **No runtime config mutation.** The scorecard does not change config to live
  mode.
- **Fail-closed promotion.** The default promotion state is `blocked` unless
  required evidence exists.
- **Conservative wording.** Documentation must not claim live readiness,
  profitability, or risk elimination.

## Components

### 1. `src/atlas_agent/agent/autonomous_paper_scorecard.py`

Core library with two public functions:

- `build_autonomous_paper_scorecard(decisions_path, manifest_path, *, replay_decisions_path=None) -> dict`
- `write_autonomous_paper_scorecard_reports(scorecard, output_dir) -> (json_path, markdown_path)`

The scorecard dict contains:

- `artifact_type`: `"autonomous_paper_scorecard"`
- `schema_version`: `1`
- `mode`: `"paper"`
- `run_id`: from the manifest
- `scorecard_dimensions`: list of per-dimension results
- `promotion_state`: one of the allowed states
- `blockers`: list of fail-closed reasons
- `safety`: safety flags (`no_live_trading`, `no_broker_calls`, etc.)

### 2. Scorecard dimensions

| Dimension | Meaning |
|---|---|
| `schema_validity` | Decisions JSONL parses and contains required fields; manifest contains required fields. |
| `replay_determinism` | All decisions share the same `run_id`; iterations are sequential; timestamps are monotonic; decision count matches manifest. Optional `replay_decisions_path` compares per-iteration state/actions. |
| `risk_gate_compliance` | Every `paper_executed` decision has `risk_result.allowed == true`; every `risk_blocked` decision has `allowed == false` and a reason. |
| `kill_switch_compliance` | No `paper_executed` decisions exist when a kill-switch violation is present; kill-switch blocks are auditable. |
| `no_live_side_effects` | All decisions and manifest report `mode == "paper"`; no live broker/provider references in artifact strings. |
| `audit_redaction` | Artifact text does not contain likely secrets (`api_key`, `token`, `password`, etc.). |
| `decision_coverage` | At least one decision exists; manifest counts match actual rows. |
| `blocked_reason_quality` | `risk_blocked` decisions include a non-empty reason and risk violations. |
| `no_trade_reason_quality` | `no_trade` decisions have `proposed_action == "hold"`, no proposed order, and a not-applicable risk result. |
| `artifact_completeness` | Both required files exist, are non-empty, and the manifest references them. |
| `future_shadow_live_prerequisites` | Run completed; demonstrated at least one executed, one no-trade, and one blocked decision; all safety dimensions pass. |

### 3. Promotion states

- `not_evaluated` — required artifact paths missing or unreadable.
- `blocked` — a critical dimension failed or the run is not suitable.
- `paper_quality_observed` — artifacts are valid and the run is well-formed, but
  does not yet meet the conservative shadow-live review prerequisites.
- `eligible_for_shadow_live_review` — all required dimensions pass and the run
  demonstrates the diversity required before any future shadow-live/read-only
  evaluation.

### 4. CLI command

`atlas agent autonomous-scorecard`

Arguments:

- `--decisions PATH` — path to `<run_id>-decisions.jsonl`
- `--manifest PATH` — path to `<run_id>-manifest.json`
- `--replay-decisions PATH` (optional) — path to a second decisions file for replay comparison
- `--output-dir DIR` — directory for `autonomous-paper-scorecard.json` and `.md`
- `--json` — emit the scorecard dict as JSON on stdout and exit 0

Exit codes:

- `0` — scorecard generated; promotion state is not `blocked`
- `1` — invalid CLI arguments
- `2` — scorecard generated but promotion state is `blocked` or `not_evaluated`

### 5. Static contract checker

`scripts/check_autonomous_paper_scorecard_contract.py`

Checks:

- `docs/autonomous-paper-scorecard.md` exists and contains required safety phrases.
- Forbidden live-readiness/profit claims are absent or negated.
- `src/atlas_agent/cli.py` registers `autonomous-scorecard`.
- `tests/test_autonomous_paper_scorecard.py` exists.

Exit codes: `0` pass, `1` blocking findings, `2` operational error.

### 6. Tests

- `tests/test_autonomous_paper_scorecard.py` — unit/integration tests for valid
  scorecard, missing/malformed artifacts, risk-blocked runs, no-trade runs,
  kill-switch blocked runs, replay mismatch, redaction, promotion defaults,
  and CLI smoke.
- `tests/test_autonomous_paper_scorecard_contract.py` — tests for the static
  checker, including failure-path injection.

### 7. Documentation and release metadata

- `docs/autonomous-paper-scorecard.md` — user-facing planning doc.
- `docs/reviews/v0.6.16-cand-002-multimodel-review-packet.md` — manual review
  handoff prompts.
- Update `docs/releases/v0.6.16-candidates.json`, `.md`, `-plan.md`, and
  `-candidate-selection.md` to list CAND-002 as implemented in planning.
- Update `CHANGELOG.md` under `[Unreleased]`.
- Update `tests/fixtures/cli_command_contract.json` to include
  `autonomous-scorecard` under the `agent` subcommands.
- Wire `scripts/check_autonomous_paper_scorecard_contract.py` and the new tests
  into `scripts/dev_check.sh` and `scripts/release_check.sh`.

## Verification commands

```bash
git status
git diff --check
python3.11 -m compileall src
python3.11 -m pytest tests/test_autonomous_paper_scorecard.py tests/test_autonomous_paper_scorecard_contract.py -q
python3.11 scripts/check_autonomous_paper_scorecard_contract.py
python3.11 -m pip check
atlas validate
atlas agent autonomous-paper --help
atlas agent autonomous-scorecard --help
atlas agent autonomous-paper --max-cycles 5 --evidence-dir reports/autonomous_paper_evidence
atlas agent autonomous-scorecard \
  --decisions reports/autonomous_paper_evidence/<run_id>/decisions.jsonl \
  --manifest reports/autonomous_paper_evidence/<run_id>/manifest.json \
  --output-dir reports/autonomous_paper_scorecard
atlas run --mode paper
atlas run --mode live  # must remain fail-closed
./scripts/release_check.sh --quick
```

## Out of scope

- Shadow-live execution.
- Live broker sync or read-only live state access.
- Provider calls.
- Version bump, tag, GitHub Release, or PyPI publication.
