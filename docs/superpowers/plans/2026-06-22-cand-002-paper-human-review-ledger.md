# CAND-002 Paper Human Review Decision Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox syntax for tracking.

**Goal:** Add `atlas backtest portfolio-review-ledger`, a deterministic paper-only non-executable human review decision ledger that consumes the CAND-001 review pack and produces `paper-human-review-ledger.json` and `paper-human-review-ledger.md`.

**Architecture:** Reuse the existing `src/atlas_agent/backtest/portfolio.py` builder/writer/renderer pattern established by CAND-001. The ledger accepts an optional pre-generated review pack path; if omitted it builds one deterministically from local sample data. Decision entries are paper-only statuses, and the gate summary explicitly denies live/broker submission while allowing paper follow-up.

**Tech Stack:** Python 3.11, argparse, `atlas_agent.backtest.portfolio`, `json`, `pathlib`.

---

## File map

| File | Responsibility |
|---|---|
| `src/atlas_agent/backtest/portfolio.py` | Add ledger constants, `build_paper_portfolio_review_ledger`, `write_portfolio_review_ledger_reports`, `render_portfolio_review_ledger_markdown`. |
| `src/atlas_agent/cli.py` | Register `portfolio-review-ledger` subparser and handler. |
| `scripts/demo_paper_human_review_ledger.sh` | Offline demo generating ledger artifacts in a temp directory. |
| `scripts/check_paper_human_review_ledger.py` | Deterministic checker with `--json`; validates files, demo, docs, schema, CLI wiring, safety flags, candidate docs. |
| `tests/test_paper_human_review_ledger.py` | Pytest coverage for CLI output, schema, determinism, safety flags, Markdown disclaimers, checker failure paths. |
| `docs/paper-human-review-ledger.md` | Feature doc with safety language and CLI examples. |
| `docs/releases/v0.6.15-plan.md` | Add CAND-002 row. |
| `docs/releases/v0.6.15-candidates.md` | Add CAND-002 bullet. |
| `docs/releases/v0.6.15-candidates.json` | Add CAND-002 object. |
| `docs/autonomy-roadmap.md` | Link CAND-002 concrete demo. |
| `docs/reviewer-checklist.md` | Add CAND-002 checklist item. |
| `docs/public-launch-readiness.md` | Add passing commands. |
| `docs/trust/README.md` | Mention CAND-002. |
| `README.md` | Add demo link. |
| `scripts/dev_check.sh` | Run checker and tests. |
| `scripts/ci_check.sh` | Run checker and tests. |
| `scripts/release_check.sh` | Run checker and tests. |
| `.github/workflows/ci.yml` | Add checker step and test file to pytest step. |

---

### Task 1: Ledger constants and builder in portfolio.py

**Files:**
- Modify: `src/atlas_agent/backtest/portfolio.py` after the review-pack section

**Spec:**
- Add constants:
  - `REVIEW_LEDGER_ARTIFACT_TYPE = "paper_human_review_ledger"`
  - `REVIEW_LEDGER_SCHEMA_VERSION = 1`
  - `REVIEW_LEDGER_RELEASE = "v0.6.15-planning"`
  - `REVIEW_LEDGER_SOURCE_RELEASE = "v0.6.14"`
  - `ALLOWED_REVIEW_LEDGER_STATUSES = {"paper_review_ledger_open", "paper_review_ledger_follow_up", "paper_review_ledger_rejected"}`
  - `ALLOWED_DECISION_STATUSES = {"paper_follow_up_allowed", "needs_more_paper_evidence", "rejected_from_paper_follow_up", "manual_review_required", "blocked_by_missing_evidence"}`
- Add `build_paper_portfolio_review_ledger(*, review_pack_path=None, output_dir=None, build_kwargs=None) -> dict`.
  - If `review_pack_path` is provided, read JSON; else call `build_paper_portfolio_review_pack(**build_kwargs)`.
  - Derive one decision entry per `review_items` in the pack.
  - Set `overall_review_ledger_status` from allowed set based on review pack status:
    - `paper_review_pack_rejected` → `paper_review_ledger_rejected`
    - `paper_review_pack_follow_up` → `paper_review_ledger_follow_up`
    - otherwise → `paper_review_ledger_open`
  - Return dict matching the required schema in the user prompt, including `gate_summary.live_approval_granted=False`, `gate_summary.broker_submission_allowed=False`, `gate_summary.paper_follow_up_allowed=True`, `real_human_approval=False`.

**Tests to write first (Task 6):**
- `test_ledger_builder_schema` asserts required fields.
- `test_ledger_builder_determinism`.

---

### Task 2: Ledger writer and Markdown renderer in portfolio.py

**Files:**
- Modify: `src/atlas_agent/backtest/portfolio.py`

**Spec:**
- Add `write_portfolio_review_ledger_reports(report, *, output_dir) -> tuple[Path, Path]` writing `paper-human-review-ledger.json` and `paper-human-review-ledger.md`.
- Add `render_portfolio_review_ledger_markdown(report) -> str` with the same all-caps safety banner style as the review pack, plus sections for Decision Entries and Gate Summary.
- JSON serialization uses `sort_keys=True, allow_nan=False`.

**Tests to write first (Task 6):**
- `test_ledger_writer_outputs_files`.
- `test_ledger_markdown_safety_phrases`.

---

### Task 3: CLI command `atlas backtest portfolio-review-ledger`

**Files:**
- Modify: `src/atlas_agent/cli.py` parser section around line 698
- Modify: `src/atlas_agent/cli.py` handler section around line 5095

**Spec:**
- Add subparser `portfolio-review-ledger` with help text describing deterministic paper-only non-ledger.
- Args: `--review-pack` (optional path), `--symbol`, `--data`, `--strategies`, `--max-strategy-weight`, `--min-cash-weight`, `--max-stressed-drawdown`, `--max-single-scenario-loss`, `--monitor-window`, `--recheck-threshold`, `--output-dir` (required), `--json`.
- Handler:
  - Import `build_paper_portfolio_review_ledger`, `write_portfolio_review_ledger_reports`.
  - If `--review-pack` provided, pass it; else build kwargs from CLI args and pass to builder.
  - Write reports.
  - Print summary or JSON.
  - Return 0 on success, 1 on exception.

**Tests to write first (Task 6):**
- `test_ledger_cli_writes_artifacts`.
- `test_ledger_cli_with_review_pack_input`.

---

### Task 4: Demo script

**Files:**
- Create: `scripts/demo_paper_human_review_ledger.sh`

**Spec:**
- `set -euo pipefail`
- Create temp dir.
- Run `atlas backtest portfolio-review-ledger --symbol DEMO-SYMBOL --data data/sample/ohlcv_extended.csv --strategies ... --output-dir $TMP`.
- Assert `paper-human-review-ledger.json` and `.md` exist.
- Inline Python assertion of schema fields and gate summary.
- Print `Paper human review ledger demo PASS` plus safety statement.
- `chmod +x` the file.

**Tests to write first (Task 6):**
- `test_demo_script_passes`.

---

### Task 5: Checker script

**Files:**
- Create: `scripts/check_paper_human_review_ledger.py`

**Spec:**
- Copy structure of `scripts/check_paper_human_review_pack.py`.
- Exit codes: 0 pass, 1 fail, 2 operational error.
- `--json` support.
- Checks:
  - Required files: `docs/paper-human-review-ledger.md`, `scripts/demo_paper_human_review_ledger.sh`, `scripts/check_paper_human_review_ledger.py`, `tests/test_paper_human_review_ledger.py`.
  - Demo script executable, uses `portfolio-review-ledger`, no live mode/broker/provider/order/credential/release/network/notification language, contains `non-executable` and `no real human approval`.
  - Docs contain required safety phrases and allowed statuses; omit forbidden claims.
  - Release metadata: version stays 0.6.14, no v0.6.15 released claim, no PyPI published true.
  - Candidate docs contain CAND-002 and planning-only.
  - CLI registers `portfolio-review-ledger` and imports the builder/writer.

**Tests to write first (Task 6):**
- `test_checker_passes_on_real_repo_and_json_parses`.
- `test_checker_fails_on_forbidden_claim`.
- `test_checker_fails_on_live_approval_language`.
- `test_checker_fails_when_cli_command_missing`.

---

### Task 6: Pytest tests

**Files:**
- Create: `tests/test_paper_human_review_ledger.py`

**Spec:**
- Follow the structure of `tests/test_paper_human_review_pack.py`.
- Import constants/functions from `atlas_agent.backtest.portfolio` and `scripts.check_paper_human_review_ledger`.
- Cover CLI output, determinism, safety flags, gate summary booleans, Markdown disclaimers, forbidden label avoidance, demo script, checker pass/fail, checker JSON output, no provider/broker/network behavior.

**Command:** `python3.11 -m pytest tests/test_paper_human_review_ledger.py -q`

---

### Task 7: Feature doc

**Files:**
- Create: `docs/paper-human-review-ledger.md`

**Spec:**
- Mirror `docs/paper-human-review-pack.md` tone and structure.
- Include v0.6.15 planning line, paper-only/offline/no-provider/no-broker/no-network banner.
- Explain it records simulated reviewed decisions over the CAND-001 review pack.
- List what it does NOT do (no live approval, no broker submission, no executable orders, etc.).
- Include CLI usage examples with `--review-pack` and without.
- List allowed ledger statuses and decision statuses.
- State human review remains required.

---

### Task 8: Update release planning docs

**Files:**
- Modify: `docs/releases/v0.6.15-plan.md`
- Modify: `docs/releases/v0.6.15-candidates.md`
- Modify: `docs/releases/v0.6.15-candidates.json`

**Spec:**
- Add CAND-002 row/bullet/object with status `proposed` and safety notes.
- Keep planning-only status and source_version 0.6.14.

---

### Task 9: Cross-reference docs

**Files:**
- Modify: `docs/autonomy-roadmap.md`
- Modify: `docs/reviewer-checklist.md`
- Modify: `docs/public-launch-readiness.md`
- Modify: `docs/trust/README.md`
- Modify: `README.md`

**Spec:**
- Add CAND-002 to candidate lists, demo links, and passing command lists where CAND-001 is already mentioned.
- Keep language consistent: paper-only, non-executable, no live readiness.

---

### Task 10: Gate integration

**Files:**
- Modify: `scripts/dev_check.sh`
- Modify: `scripts/ci_check.sh`
- Modify: `scripts/release_check.sh`
- Modify: `.github/workflows/ci.yml`

**Spec:**
- In the paper portfolio proposal sandbox section, run `scripts/check_paper_human_review_ledger.py` after the review-pack checker.
- In pytest lists, append `tests/test_paper_human_review_ledger.py`.
- In `.github/workflows/ci.yml`, add a `Paper human review ledger check` step and add the test file to the existing pytest step.

---

### Task 11: Validation and commit

**Commands:**
- `python3.11 scripts/check_paper_human_review_ledger.py`
- `python3.11 scripts/check_paper_human_review_ledger.py --json`
- `bash scripts/demo_paper_human_review_ledger.sh`
- `python3.11 -m pytest tests/test_paper_human_review_ledger.py -q`
- `./scripts/dev_check.sh`
- `./scripts/ci_check.sh`
- `./scripts/release_check.sh --quick`
- `git diff --check`
- `git diff --name-status -- src/atlas_agent/config src/atlas_agent/brokers src/atlas_agent/execution src/atlas_agent/safety src/atlas_agent/risk`

**Commit:**
```bash
git add <explicit files>
git commit -m "feat: add paper human review ledger gate"
git push origin main
```

---

## Safety invariants to preserve

- No source/package version bump (stay 0.6.14).
- No v0.6.15 tag or GitHub Release.
- No PyPI publish.
- No live trading, live submit, broker calls, provider calls, notifications, executable orders, real human approval.
- No profit, absolute-safety, claims that risk is eliminated, or live-readiness claims.
- No changes to protected runtime boundaries (`config`, `brokers`, `execution`, `safety`, `risk`).
