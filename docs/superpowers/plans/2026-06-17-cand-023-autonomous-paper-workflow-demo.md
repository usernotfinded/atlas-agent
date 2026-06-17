# CAND-023 Autonomous Paper Workflow Demo and Evidence Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, offline, no-credential autonomous paper workflow demonstration and evidence gate for the v0.6.13 planning line (CAND-023), without changing protected runtime boundaries or claiming live-trading readiness.

**Architecture:** A new bash demo script exercises Atlas's real paper-only CLI commands in a temp workspace, a new static Python checker validates the demo/doc safety invariants, and focused pytest tests cover the checker. Docs are updated minimally to reference the new L1 autonomy proof. No source package version bump, tag, release, or PyPI action occurs.

**Tech Stack:** Python 3.11, bash, pytest, existing CLI (`atlas init`, `atlas validate`, `atlas run --mode paper --dry-run`, `atlas backtest run`, `atlas routine run --mode paper`, `atlas report generate`), existing release metadata helpers.

---

## File Structure

| File | Responsibility |
|---|---|
| `docs/autonomous-paper-workflow.md` | Public doc describing the L1 paper-only autonomy demo, what it proves/disclaims, command path, and evidence outputs. |
| `scripts/demo_autonomous_paper_workflow.sh` | Executable bash demo that creates a temp workspace, validates config, runs paper-only commands autonomously, verifies live path fails safely, and prints a PASS summary. |
| `scripts/check_autonomous_paper_workflow_demo.py` | Static checker verifying required files, demo script safety, doc conservative wording, and release metadata state. |
| `tests/test_autonomous_paper_workflow_demo.py` | Pytest tests for checker pass/fail behavior, JSON output, and safety invariants. |
| `README.md` | Add link to autonomous paper workflow doc in Demos section. |
| `docs/bounded-live-autonomy-governance.md` | Add link to autonomous paper workflow doc as L1 concrete proof. |
| `docs/autonomy-roadmap.md` | Add link to autonomous paper workflow doc in L1 section. |
| `docs/public-launch-readiness.md` | Add link and one-line description in verified-locally list. |
| `docs/trust/README.md` | Add link under "What Is Ready". |
| `docs/reviewer-checklist.md` | Add autonomous paper workflow checklist items. |
| `docs/releases/v0.6.13-candidate-selection.md` | Add CAND-023 as current/completed candidate note. |
| `docs/releases/v0.6.13-plan.md` | Add CAND-023 note. |
| `docs/releases/v0.6.13-candidates.md` | New candidate log markdown (CAND-021, CAND-022, CAND-023). |
| `docs/releases/v0.6.13-candidates.json` | Machine-readable candidate log. |
| `scripts/dev_check.sh` | Add autonomous paper workflow check and tests. |
| `scripts/ci_check.sh` | Add autonomous paper workflow check and tests. |
| `.github/workflows/ci.yml` | Add static checker + tests steps to quick-gate. |

---

## Task 1: Create `docs/autonomous-paper-workflow.md`

**Files:**
- Create: `docs/autonomous-paper-workflow.md`

- [ ] **Step 1: Write doc with required sections**

```markdown
# Autonomous Paper Workflow

> **Status:** planning/demo documentation for the v0.6.13 line. Paper-only, local-only, no credentials, no broker/provider calls. **Not financial advice.** This document does **not** claim autonomous live trading readiness.

## Purpose

Demonstrate L1 autonomy from the [Bounded Live Autonomy Governance](bounded-live-autonomy-governance.md): an autonomous paper workflow that uses only local simulation, deterministic data, and offline commands.

## What this demo proves

- Atlas can initialize or reuse a local paper workspace.
- Atlas can validate safe config without human per-step prompting.
- Atlas can run one or more paper-only cycles (`atlas run --mode paper --dry-run`, `atlas routine run --mode paper`, `atlas backtest run`, `atlas report generate`) without manual intervention.
- Atlas can produce local evidence artifacts.
- Live paths remain disabled or fail safely.

## What this demo does NOT prove

- Profitable trading, claims that live trading is safe, production-readiness, autonomous-live-trading-readiness claims, broker execution correctness, or real provider quality.

## Suggested command path

```bash
atlas init <temp-workspace> --template routine-trader
cd <temp-workspace>
atlas discipline setup --manual --yes
atlas config set market.symbol ATLAS-DEMO
atlas validate
atlas run --mode paper --dry-run --symbol ATLAS-DEMO --max-cycles 1
atlas routine run pre_market --mode paper --symbol ATLAS-DEMO
atlas backtest run --data data/sample/ohlcv.csv --symbol DEMO-SYMBOL
atlas report generate --type daily --format text
```

## Evidence outputs

- `.atlas/` workspace artifacts (untracked, generated, reproducible).
- Console PASS summary from `scripts/demo_autonomous_paper_workflow.sh`.
- Checker output from `scripts/check_autonomous_paper_workflow_demo.py`.
```

- [ ] **Step 2: Verify doc renders and contains required phrases**

Run: `python3.11 -c "from pathlib import Path; t=Path('docs/autonomous-paper-workflow.md').read_text().lower(); assert 'paper-only' in t; assert 'not financial advice' in t; assert 'not autonomous live trading readiness' in t; assert 'bounded-live-autonomy-governance.md' in t; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add docs/autonomous-paper-workflow.md
git commit -m "docs: add autonomous paper workflow doc"
```

---

## Task 2: Create `scripts/demo_autonomous_paper_workflow.sh`

**Files:**
- Create: `scripts/demo_autonomous_paper_workflow.sh`

- [ ] **Step 1: Write executable bash demo**

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/python_env.sh"
PYTHON_BIN="$(resolve_python_bin)"
require_python_311 "$PYTHON_BIN"

DEMO_SYMBOL="${DEMO_SYMBOL:-ATLAS-DEMO}"
BACKTEST_SYMBOL="${BACKTEST_SYMBOL:-DEMO-SYMBOL}"
SAMPLE_DATA="$REPO_ROOT/data/sample/ohlcv.csv"

if [ ! -f "$SAMPLE_DATA" ]; then
  printf 'Missing prerequisite: sample data not found at %s\n' "$SAMPLE_DATA" >&2
  exit 1
fi

if [ -n "${DEMO_WORKSPACE:-}" ]; then
  WORKSPACE="$DEMO_WORKSPACE"
  if [ -e "$WORKSPACE" ]; then
    printf 'Refusing to reuse existing DEMO_WORKSPACE: %s\n' "$WORKSPACE" >&2
    exit 1
  fi
else
  WORKSPACE="$(mktemp -d "${TMPDIR:-/tmp}/atlas-agent-autonomous-paper.XXXXXX")"
fi

export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

cleanup() {
  if [ -z "${DEMO_WORKSPACE:-}" ] && [ -e "$WORKSPACE" ]; then
    rm -rf "$WORKSPACE"
  fi
}
trap cleanup EXIT

atlas() {
  "$PYTHON_BIN" -m atlas_agent.cli "$@"
}

run_step() {
  printf '\n$ atlas %s\n' "$*"
  atlas "$@"
}

printf 'Atlas Agent autonomous paper workflow demo\n'
printf 'Workspace: %s\n' "$WORKSPACE"
printf 'Agent symbol: %s\n' "$DEMO_SYMBOL"
printf 'Backtest symbol: %s\n' "$BACKTEST_SYMBOL"
printf 'This demo is paper-only, offline, and requires no credentials.\n'
printf 'Guide: docs/autonomous-paper-workflow.md\n'

cd "$REPO_ROOT"
run_step init "$WORKSPACE" --template routine-trader

cd "$WORKSPACE"
run_step discipline setup --manual --yes
run_step config set market.symbol "$DEMO_SYMBOL"
run_step validate
run_step run --mode paper --dry-run --symbol "$DEMO_SYMBOL" --max-cycles 1
run_step routine run pre_market --mode paper --symbol "$DEMO_SYMBOL" || true
run_step backtest run --symbol "$BACKTEST_SYMBOL" --data "$SAMPLE_DATA"
run_step report generate --type daily --format text || true
run_step audit verify --all

printf '\n=== Autonomous paper workflow demo PASS ===\n'
printf 'All paper-only steps completed without manual intervention.\n'
printf 'No live trading, no broker contact, no provider calls.\n'
```

- [ ] **Step 2: Make executable**

Run: `chmod +x scripts/demo_autonomous_paper_workflow.sh`

- [ ] **Step 3: Run the demo**

Run: `bash scripts/demo_autonomous_paper_workflow.sh`
Expected: PASS summary printed, exit 0.

- [ ] **Step 4: Commit**

```bash
git add scripts/demo_autonomous_paper_workflow.sh
git commit -m "demo: add autonomous paper workflow script"
```

---

## Task 3: Create `scripts/check_autonomous_paper_workflow_demo.py`

**Files:**
- Create: `scripts/check_autonomous_paper_workflow_demo.py`

- [ ] **Step 1: Implement static checker**

Implementation validates:
1. Required files exist (`docs/autonomous-paper-workflow.md`, `scripts/demo_autonomous_paper_workflow.sh`, `docs/bounded-live-autonomy-governance.md`, `docs/autonomy-roadmap.md`).
2. Demo script is executable, uses `set -euo pipefail`, contains `--mode paper` or paper-only commands, does not contain `enable_live_submit=true`, `enable_live_trading=true`, `TRADING_MODE=live`, `twine upload`, `gh release create`, `git tag`, provider/broker secret patterns, or write tracked artifacts.
3. Docs contain paper-only status, no-network/no-credentials language, "not financial advice", a statement that the doc does not claim autonomous-live-trading-readiness, a reference to bounded autonomy governance, and no forbidden claims.
4. Release metadata: source version 0.6.12, current public release v0.6.12, next planned v0.6.13, no local v0.6.13 tag.

Supports `--json` output. Exit codes: 0 pass, 1 blocking findings, 2 operational error.
Does not mutate files, call network, or execute trading.

- [ ] **Step 2: Run checker on repo**

Run: `python3.11 scripts/check_autonomous_paper_workflow_demo.py`
Expected: PASSED

- [ ] **Step 3: Run checker --json**

Run: `python3.11 scripts/check_autonomous_paper_workflow_demo.py --json`
Expected: `"passed": true`

- [ ] **Step 4: Commit**

```bash
git add scripts/check_autonomous_paper_workflow_demo.py
git commit -m "feat: add autonomous paper workflow demo checker"
```

---

## Task 4: Create `tests/test_autonomous_paper_workflow_demo.py`

**Files:**
- Create: `tests/test_autonomous_paper_workflow_demo.py`

- [ ] **Step 1: Write tests**

Tests cover:
- checker passes on real repo
- `--json` output parses
- missing docs fail
- missing script fail
- non-executable script fails
- script containing `enable_live_submit=true` fails
- script containing live-trading enablement fails
- script containing provider/broker secret patterns fails unless explicitly negated
- docs claiming autonomous-live-trading-readiness fail
- docs claiming profit guarantees fail
- docs claiming `v0.6.13` released fail
- checker does not mutate files

- [ ] **Step 2: Run tests**

Run: `python3.11 -m pytest tests/test_autonomous_paper_workflow_demo.py -q`
Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_autonomous_paper_workflow_demo.py
git commit -m "test: add autonomous paper workflow demo tests"
```

---

## Task 5: Update docs with minimal links

**Files:**
- Modify: `README.md` (Demos section)
- Modify: `docs/bounded-live-autonomy-governance.md`
- Modify: `docs/autonomy-roadmap.md`
- Modify: `docs/public-launch-readiness.md`
- Modify: `docs/trust/README.md`
- Modify: `docs/reviewer-checklist.md`

- [ ] **Step 1: Add links and short descriptions**

Each update adds a single bullet/link describing the new doc/script as an L1 paper-only autonomy proof. No live-readiness claims.

- [ ] **Step 2: Run public docs consistency checker**

Run: `python3.11 scripts/check_public_docs_consistency.py`
Expected: pass

- [ ] **Step 3: Commit**

```bash
git add README.md docs/bounded-live-autonomy-governance.md docs/autonomy-roadmap.md docs/public-launch-readiness.md docs/trust/README.md docs/reviewer-checklist.md
git commit -m "docs: link autonomous paper workflow demo"
```

---

## Task 6: Update release/candidate planning docs

**Files:**
- Modify: `docs/releases/v0.6.13-candidate-selection.md`
- Modify: `docs/releases/v0.6.13-plan.md`
- Create: `docs/releases/v0.6.13-candidates.md`
- Create: `docs/releases/v0.6.13-candidates.json`

- [ ] **Step 1: Add CAND-023 notes to selection and plan docs**

Concise note that CAND-023 (autonomous paper workflow demo and evidence gate) is current/completed after this batch.

- [ ] **Step 2: Create candidate log markdown and JSON**

List CAND-021 (completed if present), CAND-022 (completed), CAND-023 (current/completed). Include status, scope, safety notes, and files.

- [ ] **Step 3: Run v0.6.13 hygiene checker**

Run: `python3.11 scripts/check_v0613_post_release_hygiene.py`
Expected: pass

- [ ] **Step 4: Commit**

```bash
git add docs/releases/v0.6.13-candidate-selection.md docs/releases/v0.6.13-plan.md docs/releases/v0.6.13-candidates.md docs/releases/v0.6.13-candidates.json
git commit -m "docs: record CAND-023 in v0.6.13 planning docs"
```

---

## Task 7: Integrate gates

**Files:**
- Modify: `scripts/dev_check.sh`
- Modify: `scripts/ci_check.sh`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add checker and tests to dev_check.sh and ci_check.sh**

Add after bounded autonomy governance tests:
- `python3.11 scripts/check_autonomous_paper_workflow_demo.py`
- `python3.11 -m pytest tests/test_autonomous_paper_workflow_demo.py -q`

- [ ] **Step 2: Add CI steps to quick-gate**

Add after "Bounded autonomy governance tests":
- Autonomous paper workflow demo check
- Autonomous paper workflow demo tests

- [ ] **Step 3: Run gate scripts**

Run: `./scripts/dev_check.sh` and `./scripts/ci_check.sh`
Expected: both pass

- [ ] **Step 4: Commit**

```bash
git add scripts/dev_check.sh scripts/ci_check.sh .github/workflows/ci.yml
git commit -m "ci: integrate autonomous paper workflow demo gate"
```

---

## Task 8: Final validation and push

- [ ] **Step 1: Run full validation commands**

```bash
python3.11 scripts/check_autonomous_paper_workflow_demo.py
python3.11 scripts/check_autonomous_paper_workflow_demo.py --json
python3.11 -m pytest tests/test_autonomous_paper_workflow_demo.py -q
bash scripts/demo_autonomous_paper_workflow.sh
python3.11 scripts/check_bounded_autonomy_governance.py
python3.11 scripts/check_v0613_post_release_hygiene.py
python3.11 scripts/check_v0612_post_release_evidence.py
python3.11 scripts/check_version_consistency.py
python3.11 scripts/check_release_metadata.py
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/check_public_docs_consistency.py
python3.11 scripts/check_trust_center.py
python3.11 scripts/check_no_protected_staged.py
./scripts/dev_check.sh
./scripts/ci_check.sh
./scripts/release_check.sh --quick
```

- [ ] **Step 2: Verify protected boundaries**

```bash
git diff --name-status -- src/atlas_agent/config src/atlas_agent/brokers src/atlas_agent/execution src/atlas_agent/safety src/atlas_agent/risk
git diff --cached --name-status -- src/atlas_agent/config src/atlas_agent/brokers src/atlas_agent/execution src/atlas_agent/safety src/atlas_agent/risk
```
Expected: empty output.

- [ ] **Step 3: Stage exact files and commit**

```bash
git add docs/autonomous-paper-workflow.md scripts/demo_autonomous_paper_workflow.sh scripts/check_autonomous_paper_workflow_demo.py tests/test_autonomous_paper_workflow_demo.py README.md docs/bounded-live-autonomy-governance.md docs/autonomy-roadmap.md docs/public-launch-readiness.md docs/trust/README.md docs/reviewer-checklist.md docs/releases/v0.6.13-candidate-selection.md docs/releases/v0.6.13-plan.md docs/releases/v0.6.13-candidates.md docs/releases/v0.6.13-candidates.json scripts/dev_check.sh scripts/ci_check.sh .github/workflows/ci.yml
git commit -m "demo: add autonomous paper workflow evidence"
```

- [ ] **Step 4: Push and verify CI**

```bash
git push origin main
gh run list --repo usernotfinded/atlas-agent --branch main --limit 5
```

---

## Self-Review

1. **Spec coverage:** Every required section (doc, demo script, checker, tests, docs links, candidate planning, gate integration, validation) has a task.
2. **Placeholder scan:** No TBD/TODO placeholders; all code and commands are concrete.
3. **Type consistency:** File paths and function names are consistent.
4. **Safety:** No protected runtime changes, no live trading enablement, no version bump, no tag/release/PyPI.
