# Paper Human Review Policy Simulator and Blocked-Live Gate — Design

**Candidate:** v0.6.15 CAND-003  
**Status:** planning-only  
**Source release:** v0.6.14  
**Target release:** v0.6.15-planning  
**Scope:** deterministic, offline, paper-only policy simulator

## Purpose

CAND-001 produced a non-executable paper human review pack.  
CAND-002 produced a paper-only human review decision ledger.  
CAND-003 adds a deterministic, offline, paper-only policy simulator that evaluates the review pack and decision ledger against explicit safety policy rules and produces a gate artifact showing which paper follow-ups are allowed and which live-related paths remain blocked.

## Non-goals

- This does NOT approve live trading.
- This does NOT enable live submit.
- This does NOT generate executable orders.
- This does NOT submit anything to brokers.
- This does NOT call providers.
- This does NOT send notifications.
- This does NOT create real human approval.
- This does NOT imply production/live readiness.

## Architecture

A single backtest portfolio module function consumes either:

1. a `paper-human-review-pack.json` artifact path and a `paper-human-review-ledger.json` artifact path, or
2. `build_kwargs` that let it deterministically generate both upstream artifacts.

It runs a fixed list of policy rules against the artifacts and emits a `paper-human-review-policy.json` artifact plus a Markdown report.  All rules are evaluated offline; no network, broker, provider, or notification path is touched.

## CLI

```bash
atlas backtest portfolio-review-policy \
  --review-pack <path> \
  --review-ledger <path> \
  --output-dir <dir> \
  [--json]
```

For deterministic self-contained demos/tests, the CLI also supports building the upstream artifacts from the same pass-through arguments used by `portfolio-review-ledger`:

```bash
atlas backtest portfolio-review-policy \
  --symbol DEMO-SYMBOL \
  --data data/sample/ohlcv_extended.csv \
  --strategies buy_and_hold,moving_average_cross \
  --output-dir <dir>
```

## Artifact schema

```json
{
  "artifact_type": "paper_human_review_policy",
  "schema_version": 1,
  "release": "v0.6.15-planning",
  "source_release": "v0.6.14",
  "mode": "paper",
  "paper_only": true,
  "non_executable": true,
  "provider_required": false,
  "broker_required": false,
  "network_required": false,
  "live_submit_enabled": false,
  "orders_generated": false,
  "notifications_sent": false,
  "real_human_approval": false,
  "not_financial_advice": true,
  "not_live_ready": true,
  "source_artifact_types": ["paper_human_review_pack", "paper_human_review_ledger"],
  "source_artifact_digests": {"paper_human_review_pack": "<sha256>", "paper_human_review_ledger": "<sha256>"},
  "overall_policy_status": "paper_policy_passed_with_live_blocked",
  "policy_rules": [...],
  "policy_results": [...],
  "gate_summary": {
    "paper_follow_up_allowed": true,
    "live_path_blocked": true,
    "broker_submission_allowed": false,
    "provider_execution_allowed": false,
    "notification_sending_allowed": false,
    "real_order_generation_allowed": false
  },
  "safety": {
    "no_live_trading": true,
    "no_broker_calls": true,
    "no_provider_calls": true,
    "no_notifications_sent": true,
    "no_orders_generated": true,
    "no_profit_claim": true,
    "no_live_readiness_claim": true,
    "no_real_human_approval": true,
    "non_executable": true,
    "paper_only": true
  }
}
```

## Policy rules

1. `require_non_executable_artifact` — artifact declares `non_executable: true`.
2. `require_paper_only_mode` — artifact declares `mode: "paper"` and `paper_only: true`.
3. `block_live_submit` — `live_submit_enabled` is `false`.
4. `block_broker_submission` — `broker_required`, `broker_submission_allowed`, and upstream `broker_submission_allowed` are `false`.
5. `block_provider_execution` — `provider_required`, `provider_execution_allowed`, and upstream `provider_required` are `false`.
6. `block_real_notifications` — `notifications_sent`, `notification_sending_allowed` are `false`.
7. `block_order_generation` — `orders_generated`, `real_order_generation_allowed` are `false`.
8. `require_manual_review_for_future_live_work` — upstream ledger contains `manual_review_required` decisions or the pack contains `needs_human_review` items.
9. `require_no_profit_claims` — upstream safety block declares `no_profit_claim: true`.
10. `require_no_absolute_safety_claims` — upstream safety block declares `no_live_readiness_claim: true` and doc language avoids forbidden claims.

## Policy result states

- `passed`
- `blocked`
- `needs_more_paper_evidence`
- `manual_review_required`

## Files

- `src/atlas_agent/backtest/portfolio.py` — simulator builder, writer, renderer, constants.
- `src/atlas_agent/cli.py` — `portfolio-review-policy` subparser and handler.
- `scripts/demo_paper_human_review_policy.sh` — offline demo.
- `scripts/check_paper_human_review_policy.py` — deterministic checker.
- `tests/test_paper_human_review_policy.py` — focused tests.
- `docs/paper-human-review-policy.md` — human-facing doc.
- `docs/releases/v0.6.15-plan.md`
- `docs/releases/v0.6.15-candidates.md`
- `docs/releases/v0.6.15-candidates.json`
- `docs/autonomy-roadmap.md`
- `scripts/dev_check.sh`
- `scripts/ci_check.sh`
- `scripts/release_check.sh`
- `.github/workflows/ci.yml`

## Safety invariants

- Source/package version remains `0.6.14`.
- No v0.6.15 tag or GitHub Release is created.
- No PyPI publish.
- No modifications to `src/atlas_agent/config`, `brokers`, `execution`, `safety`, or `risk` unless absolutely required.
- All policy decisions are paper-only and non-executable.
- Live path is explicitly blocked in the gate summary.
