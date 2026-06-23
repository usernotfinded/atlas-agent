# CAND-001 Paper Autonomous Decision Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox
> syntax for tracking.

**Goal:** Implement a deterministic, paper-only autonomous decision loop (CAND-001) with
a shadow-live readiness contract, CLI entrypoint, tests, docs, checkers, and v0.6.16
release-planning metadata — without enabling live trading, broker submission, or real
provider calls.

**Architecture:** Reuse the existing backtest data loader, strategy registry, execution
simulator, and `RiskManager` paper-mode evaluation inside a new loop module. Expose the
loop through a new `atlas agent autonomous-paper` subcommand. Write decision JSONL and
manifest JSON to `reports/autonomous_paper/`. Add planning-only docs and deterministic
static checkers for the paper loop and shadow-live contract.

**Tech Stack:** Python 3.11, Pydantic, existing Atlas Agent backtest/risk/audit/event
infrastructure.

---

### Task 1: Core autonomous paper loop module

**Files:**
- Create: `src/atlas_agent/agent/autonomous_paper.py`

- [ ] **Step 1: Define decision and result models**

  Implement `AutonomousDecision` and `AutonomousPaperResult` Pydantic models with the
  fields required by CAND-001.

- [ ] **Step 2: Implement loop driver**

  Implement `run_autonomous_paper_loop()` to load local bars, iterate up to
  `max_cycles`, call the strategy, evaluate the first proposed order through
  `RiskManager.evaluate_order(..., mode="paper")`, simulate fills with
  `ExecutionSimulator`, and write audit events.

- [ ] **Step 3: Add evidence bundle helper**

  Implement `build_autonomous_paper_evidence()` to copy redacted decision/manifest
  files into a local evidence directory with checksums.

---

### Task 2: CLI integration

**Files:**
- Modify: `src/atlas_agent/cli.py` (parser registration + dispatch branch)
- Modify: `src/atlas_agent/audit/models.py` (add autonomous-paper audit event types)
- Modify: `src/atlas_agent/events/schema.py` (add autonomous-paper event types)

- [ ] **Step 1: Register parser**

  Add `agent_sub.add_parser("autonomous-paper")` with `--symbol`, `--strategy`,
  `--data-path`, `--max-cycles`, `--evidence-dir`, and `--json`.

- [ ] **Step 2: Add dispatch branch**

  In `main()`, call `_check_discipline_or_exit(config)` and
  `run_autonomous_paper_loop(mode="paper", ...)`.

- [ ] **Step 3: Extend event type registries**

  Add autonomous-paper event types to audit and events schemas so the loop can log
  safely.

---

### Task 3: Shadow-live contract and static checkers

**Files:**
- Create: `docs/autonomous-paper-loop.md`
- Create: `docs/shadow-live-readiness-contract.md`
- Create: `scripts/check_autonomous_paper_loop_contract.py`
- Create: `scripts/check_shadow_live_contract.py`
- Create: `tests/test_autonomous_paper_loop_contract.py`
- Create: `tests/test_shadow_live_contract.py`

- [ ] **Step 1: Write planning-only docs**

  Include status, not-financial-advice disclaimer, safety boundaries, CLI usage, and
  cross-references to `bounded-live-autonomy-governance.md`.

- [ ] **Step 2: Implement deterministic checkers**

  Follow existing checker patterns; verify required files, required phrases, and
  forbidden claims.

- [ ] **Step 3: Add checker tests**

  Test pass on the real repo, JSON output, and failure when a forbidden phrase is
  injected.

---

### Task 4: Unit and integration tests

**Files:**
- Create: `tests/test_autonomous_paper_loop.py`

- [ ] **Step 1: Happy path**

  `buy_and_hold` with `position_pct=0.2` produces at least one paper execution.

- [ ] **Step 2: No-trade path**

  `moving_average_cross` on the first three bars produces only `no_trade` decisions.

- [ ] **Step 3: Risk-blocked path**

  `symbol_allowlist=["OTHER"]` blocks every proposed order.

- [ ] **Step 4: Malformed config fail-closed**

  Missing symbol or missing data path returns `status="failed"` with zero decisions.

- [ ] **Step 5: Live mode rejected**

  `atlas agent autonomous-paper --mode live` raises `SystemExit` because `--mode` is
  not a registered argument.

- [ ] **Step 6: Broker submit and provider execution unreachable**

  Monkeypatch `BrokerResolver.resolve_execution_broker` and
  `get_provider_from_runtime_config` and assert neither is called.

- [ ] **Step 7: Audit artifacts and deterministic replay**

  Manifest and audit log exist; two runs with identical inputs produce identical
  decision states.

---

### Task 5: Release planning metadata

**Files:**
- Modify: `docs/releases/v0.6.16-plan.md`
- Modify: `docs/releases/v0.6.16-candidates.md`
- Modify: `docs/releases/v0.6.16-candidates.json`
- Modify: `docs/releases/v0.6.16-candidate-selection.md`
- Modify: `docs/bounded-live-autonomy-governance.md`
- Modify: `CHANGELOG.md`
- Modify: `scripts/dev_check.sh`
- Modify: `scripts/release_check.sh`

- [ ] **Step 1: Update candidate docs**

  Mark CAND-001 as implemented in the v0.6.16 planning seed.

- [ ] **Step 2: Update governance doc**

  Add CAND-001 and shadow-live contract to the current-release-truth section.

- [ ] **Step 3: Update CHANGELOG**

  Add CAND-001 entries under `[Unreleased]`; do not create a `[0.6.16]` header.

- [ ] **Step 4: Wire checkers into release gates**

  Add autonomous-paper/shadow-live checker and test invocations to
  `dev_check.sh` and `release_check.sh`.

---

### Task 6: Verification

- [ ] `python3.11 -m compileall src`
- [ ] `python3.11 -m pytest tests/test_autonomous_paper_loop.py tests/test_autonomous_paper_loop_contract.py tests/test_shadow_live_contract.py -v`
- [ ] `python3.11 scripts/check_autonomous_paper_loop_contract.py`
- [ ] `python3.11 scripts/check_shadow_live_contract.py`
- [ ] `python3.11 scripts/check_forbidden_claims.py`
- [ ] `python3.11 scripts/check_bounded_autonomy_governance.py`
- [ ] `python3.11 scripts/check_public_docs_consistency.py`
- [ ] `python3.11 scripts/check_release_metadata.py`
- [ ] `python3.11 scripts/check_trust_center.py`
- [ ] `git diff --check`
- [ ] `./scripts/release_check.sh --quick` (or closest equivalent)
