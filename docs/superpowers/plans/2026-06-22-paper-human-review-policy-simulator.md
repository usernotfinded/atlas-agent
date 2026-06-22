# Paper Human Review Policy Simulator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add v0.6.15 CAND-003 — a deterministic, offline, paper-only policy simulator that evaluates the CAND-001 review pack and CAND-002 review ledger against explicit safety rules and emits a blocked-live gate artifact.

**Architecture:** Extend `src/atlas_agent/backtest/portfolio.py` with a new builder/writer/renderer trio. Add a `atlas backtest portfolio-review-policy` CLI command. Provide a demo script, checker, tests, docs, and gate integration mirroring CAND-001/CAND-002.

**Tech Stack:** Python 3.11, argparse, existing atlas-agent backtest portfolio module.

---

### Task 1: Implement policy simulator core in `src/atlas_agent/backtest/portfolio.py`

**Files:**
- Modify: `src/atlas_agent/backtest/portfolio.py`

**New constants:**

```python
REVIEW_POLICY_ARTIFACT_TYPE = "paper_human_review_policy"
REVIEW_POLICY_SCHEMA_VERSION = 1
REVIEW_POLICY_RELEASE = "v0.6.15-planning"
REVIEW_POLICY_SOURCE_RELEASE = "v0.6.14"

ALLOWED_REVIEW_POLICY_STATUSES = {
    "paper_policy_passed_with_live_blocked",
    "paper_policy_needs_more_evidence",
    "paper_policy_manual_review_required",
    "paper_policy_blocked",
}

ALLOWED_POLICY_RESULT_STATES = {"passed", "blocked", "needs_more_paper_evidence", "manual_review_required"}
```

**New function:**

```python
def build_paper_portfolio_review_policy(
    *,
    review_pack_path=None,
    review_ledger_path=None,
    output_dir=None,
    build_kwargs=None,
) -> dict[str, Any]:
    # Load or build pack and ledger; validate artifact_type/schema_version; compute digests.
    # Evaluate policy_rules and produce policy_results.
    # Return artifact dict with gate_summary blocking all live paths.
```

**New writer:**

```python
def write_portfolio_review_policy_reports(report, *, output_dir) -> tuple[Path, Path]:
    # Write paper-human-review-policy.json and .md.
```

**New renderer:**

```python
def render_portfolio_review_policy_markdown(report) -> str:
    # Emit bold safety header, policy rules/results table, gate summary, and disclaimers.
```

- [ ] **Step 1: Write failing test** in `tests/test_paper_human_review_policy.py` asserting `build_paper_portfolio_review_policy` exists and returns `artifact_type == "paper_human_review_policy"`.
- [ ] **Step 2: Run test to verify it fails.**
- [ ] **Step 3: Add constants and function to `portfolio.py`.**
- [ ] **Step 4: Run test to verify it passes.**
- [ ] **Step 5: Add writer and renderer; run determinism and schema tests.**

---

### Task 2: Add `atlas backtest portfolio-review-policy` CLI command

**Files:**
- Modify: `src/atlas_agent/cli.py`

Add subparser after `portfolio-review-ledger`:

```python
backtest_portfolio_review_policy = backtest_sub.add_parser(
    "portfolio-review-policy",
    help=(
        "Run a deterministic paper-only policy simulation against a review pack and ledger. "
        "No provider, broker, network, live trading, notification, order, or real human approval path is used."
    ),
)
backtest_portfolio_review_policy.add_argument("--review-pack", default=None)
backtest_portfolio_review_policy.add_argument("--review-ledger", default=None)
backtest_portfolio_review_policy.add_argument("--symbol", default=None)
backtest_portfolio_review_policy.add_argument("--data", default=None)
backtest_portfolio_review_policy.add_argument("--strategies", default=None)
backtest_portfolio_review_policy.add_argument("--max-strategy-weight", type=float, default=0.40)
backtest_portfolio_review_policy.add_argument("--min-cash-weight", type=float, default=0.10)
backtest_portfolio_review_policy.add_argument("--max-stressed-drawdown", type=float, default=0.25)
backtest_portfolio_review_policy.add_argument("--max-single-scenario-loss", type=float, default=0.20)
backtest_portfolio_review_policy.add_argument("--monitor-window", type=int, default=20)
backtest_portfolio_review_policy.add_argument("--recheck-threshold", type=float, default=0.05)
backtest_portfolio_review_policy.add_argument("--output-dir", required=True)
backtest_portfolio_review_policy.add_argument("--json", action="store_true")
```

Add handler branch after `portfolio-review-ledger`:

```python
if args.backtest_command == "portfolio-review-policy":
    try:
        from atlas_agent.backtest.portfolio import build_paper_portfolio_review_policy, write_portfolio_review_policy_reports
        if getattr(args, "review_pack", None) and getattr(args, "review_ledger", None):
            report = build_paper_portfolio_review_policy(
                review_pack_path=getattr(args, "review_pack"),
                review_ledger_path=getattr(args, "review_ledger"),
            )
        else:
            strategy_ids = parse_strategy_list(getattr(args, "strategies", None))
            report = build_paper_portfolio_review_policy(
                build_kwargs={
                    "data_path": getattr(args, "data"),
                    "symbol": getattr(args, "symbol"),
                    "strategies": strategy_ids,
                    "max_strategy_weight": getattr(args, "max_strategy_weight", 0.40),
                    "min_cash_weight": getattr(args, "min_cash_weight", 0.10),
                    "max_stressed_drawdown": getattr(args, "max_stressed_drawdown", 0.25),
                    "max_single_scenario_loss": getattr(args, "max_single_scenario_loss", 0.20),
                    "monitor_window": getattr(args, "monitor_window", 20),
                    "recheck_threshold": getattr(args, "recheck_threshold", 0.05),
                }
            )
        json_path, md_path = write_portfolio_review_policy_reports(report, output_dir=getattr(args, "output_dir"))
    except Exception as exc:
        print(f"Error: {exc}")
        return 1

    if getattr(args, "json", False):
        import json
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
        return 0

    print(f"Paper human review policy simulation generated: {report.get('symbol', 'n/a')}")
    print(f"Overall policy status: {report['overall_policy_status']}")
    print(f"Policy rules evaluated: {len(report['policy_rules'])}")
    print(f"Live path blocked: {report['gate_summary']['live_path_blocked']}")
    print(f"Broker submission allowed: {report['gate_summary']['broker_submission_allowed']}")
    print(f"Paper follow-up allowed: {report['gate_summary']['paper_follow_up_allowed']}")
    print(f"Report saved to: {json_path}")
    print(f"Markdown saved to: {md_path}")
    print("Non-executable. No live trading, broker calls, provider calls, network calls, notifications, orders, or real human approval.")
    return 0
```

- [ ] **Step 1: Write failing CLI test** invoking `atlas backtest portfolio-review-policy --help`.
- [ ] **Step 2: Add subparser and handler.**
- [ ] **Step 3: Run CLI test to verify it passes.**

---

### Task 3: Add demo script

**Files:**
- Create: `scripts/demo_paper_human_review_policy.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3.11}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TMPDIR=$(mktemp -d -t atlas-paper-human-review-policy.XXXXXX)
trap 'rm -rf "$TMPDIR"' EXIT

$PYTHON_BIN -m atlas_agent.cli backtest portfolio-review-policy \
  --symbol DEMO-SYMBOL \
  --data data/sample/ohlcv_extended.csv \
  --strategies buy_and_hold,moving_average_cross \
  --output-dir "$TMPDIR"

# assert files exist and schema/gate invariants
$PYTHON_BIN - <<"PY" "$TMPDIR"
import json, sys
output_dir = sys.argv[1]
with open(f"{output_dir}/paper-human-review-policy.json") as f:
    report = json.load(f)
assert report["artifact_type"] == "paper_human_review_policy"
assert report["schema_version"] == 1
assert report["release"] == "v0.6.15-planning"
assert report["source_release"] == "v0.6.14"
assert report["mode"] == "paper"
assert report["non_executable"] is True
assert report["paper_only"] is True
assert report["provider_required"] is False
assert report["broker_required"] is False
assert report["network_required"] is False
assert report["live_submit_enabled"] is False
assert report["orders_generated"] is False
assert report["notifications_sent"] is False
assert report["real_human_approval"] is False
assert report["not_financial_advice"] is True
assert report["not_live_ready"] is True
assert report["gate_summary"]["live_path_blocked"] is True
assert report["gate_summary"]["broker_submission_allowed"] is False
assert report["gate_summary"]["provider_execution_allowed"] is False
assert report["gate_summary"]["notification_sending_allowed"] is False
assert report["gate_summary"]["real_order_generation_allowed"] is False
assert report["gate_summary"]["paper_follow_up_allowed"] is True
PY

echo "Paper human review policy simulation complete."
echo "Artifacts: $TMPDIR/paper-human-review-policy.json $TMPDIR/paper-human-review-policy.md"
echo "Non-executable. No network, broker, provider, notification, order, or real human approval path was used."
```

- [ ] **Step 1: Create demo script and make executable.**
- [ ] **Step 2: Run demo script; fix failures.**

---

### Task 4: Add checker script

**Files:**
- Create: `scripts/check_paper_human_review_policy.py`

Mirror `scripts/check_paper_human_review_ledger.py` with:

- Required files: `docs/paper-human-review-policy.md`, `scripts/demo_paper_human_review_policy.sh`, `scripts/check_paper_human_review_policy.py`, `tests/test_paper_human_review_policy.py`.
- Demo checks: executable, contains `portfolio-review-policy`, no `--mode live`, no broker/order/provider commands, no credentials, no tag/release/publish commands, no notification services, contains required safety phrases.
- Doc checks: required safety phrases, allowed statuses, forbidden claims.
- Release metadata: version `0.6.14`, no v0.6.15 released claim, no PyPI published claim.
- CAND-003 candidate doc checks.
- CLI wiring: `portfolio-review-policy`, `build_paper_portfolio_review_policy`, `write_portfolio_review_policy_reports` appear in `src/atlas_agent/cli.py`.
- `--json` support; exit codes `0/1/2`.

- [ ] **Step 1: Write checker.**
- [ ] **Step 2: Run checker on clean repo; verify pass.**
- [ ] **Step 3: Run checker `--json`; verify parseable output.**

---

### Task 5: Add tests

**Files:**
- Create: `tests/test_paper_human_review_policy.py`

Cover:

- CLI produces JSON and Markdown.
- Output is deterministic.
- Schema contains `non_executable: true`, `paper_only: true`, `mode: "paper"`.
- `broker_required`, `provider_required`, `network_required`, `live_submit_enabled`, `orders_generated`, `notifications_sent`, `real_human_approval` are `false`.
- `gate_summary` blocks live path, broker submission, provider execution, notification sending, real order generation; allows paper follow-up.
- Markdown contains safety disclaimers.
- Checker passes on clean repo and `--json` parses.
- Negative checker tests: inject forbidden claims, executable order language, live-approval language, missing docs.
- No provider/broker calls in demo path.

- [ ] **Step 1: Write failing tests.**
- [ ] **Step 2: Implement core until tests pass.**
- [ ] **Step 3: Run full test file; fix failures.**

---

### Task 6: Add human-facing doc

**Files:**
- Create: `docs/paper-human-review-policy.md`

Include:

- Bold safety header: paper-only, non-executable, not financial advice, not live ready.
- What the simulator does and does NOT do.
- CLI usage examples.
- Policy rules list.
- Gate summary explanation.
- No live trading / no broker / no provider / no notifications / no orders / no real human approval disclaimers.
- Human review remains required before any future live-related work.

- [ ] **Step 1: Write doc.**
- [ ] **Step 2: Run forbidden-claims scan; fix any findings.**

---

### Task 7: Update release planning and roadmap docs

**Files:**
- Modify: `docs/releases/v0.6.15-plan.md`
- Modify: `docs/releases/v0.6.15-candidates.md`
- Modify: `docs/releases/v0.6.15-candidates.json`
- Modify: `docs/autonomy-roadmap.md`

Add CAND-003 entries following CAND-001/CAND-002 pattern. Set status to `implemented` once code is complete.

- [ ] **Step 1: Add CAND-003 row in plan.md.**
- [ ] **Step 2: Add CAND-003 bullet in candidates.md.**
- [ ] **Step 3: Add CAND-003 object in candidates.json.**
- [ ] **Step 4: Add link in autonomy-roadmap.md.**

---

### Task 8: Integrate into gates

**Files:**
- Modify: `scripts/dev_check.sh`
- Modify: `scripts/ci_check.sh`
- Modify: `scripts/release_check.sh`
- Modify: `.github/workflows/ci.yml`

Add `scripts/check_paper_human_review_policy.py` invocation and `tests/test_paper_human_review_policy.py` to the pytest lists where CAND-001/CAND-002 appear.

- [ ] **Step 1: Update dev_check.sh.**
- [ ] **Step 2: Update ci_check.sh.**
- [ ] **Step 3: Update release_check.sh.**
- [ ] **Step 4: Update .github/workflows/ci.yml.**
- [ ] **Step 5: Run all gates; fix failures.**

---

### Task 9: Final validation and push

- [ ] **Step 1: Run all Phase 8 validation commands.**
- [ ] **Step 2: Verify protected runtime boundaries unchanged.**
- [ ] **Step 3: Stage explicit files, commit, push to main.**
- [ ] **Step 4: Verify GitHub Actions CI is green.**
