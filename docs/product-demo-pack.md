# Atlas Agent Product Demo and Marketplace Readiness Pack

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## Purpose

This pack collects the reproducible, credential-free demos and preflight artifacts that reviewers and marketplace evaluators can run to verify Atlas Agent's paper-first, safe-by-default design. It is intended for sandbox and preflight evaluation only: live trading is disabled by default, provider execution remains locked, broker order submission is blocked by `can_submit=false`, and no API keys or broker credentials are required. Use this pack to confirm that Atlas behaves as a local-first, broker-neutral supervised workspace before any real-money or production discussion.

## Prerequisites

- **Python 3.11 or newer** installed locally.
- A cloned copy of the repository:

  ```bash
  git clone https://github.com/usernotfinded/atlas-agent.git
  cd atlas-agent
  ```

- Install the package in editable mode:

  ```bash
  python3.11 -m pip install -e .
  ```

- Verify the bundled sample data is present:

  ```bash
  test -f data/sample/ohlcv.csv && echo "sample data OK"
  ```

- No broker credentials, provider API keys, `.env.atlas` file, or live-trading configuration are required for the default demo path.

All default demos are paper-only, offline, and sandbox-first. Live trading, provider execution, and broker order submission remain disabled unless explicitly and separately configured.

## Exact commands

Run everything from the repository root. No broker credentials, API keys, or network access are required.

### One-line demo

```bash
python3.11 -m pip install -e .
./scripts/demo_product_walkthrough.sh
```

This creates an isolated temporary workspace, validates paper mode, runs redacted local diagnostics, prints a paper dry-run, executes the deterministic `DEMO-SYMBOL` backtest against `data/sample/ohlcv.csv`, and verifies local artifacts. Use `--keep-workspace` to inspect the generated workspace after the run.

### Manual paper-and-research command sequence

```bash
# 1. Install the local checkout
python3.11 -m pip install -e .

# 2. Create and enter an isolated paper workspace
atlas init product-demo-workspace --template routine-trader
cd product-demo-workspace

# 3. Required safe discipline profile
atlas discipline setup --manual --yes

# 4. Use the documentation-only demo symbol
atlas config set market.symbol ATLAS-DEMO

# 5. Confirm paper mode and disabled live trading
atlas validate
atlas doctor --json

# 6. Print the paper plan without provider or broker contact
atlas run --mode paper --dry-run --symbol ATLAS-DEMO

# 7. Run the deterministic local backtest
atlas backtest run --data data/sample/ohlcv.csv --symbol DEMO-SYMBOL

# 8. Inspect local evidence
atlas backtest runs --validate --json
atlas audit verify --all
```

### Research sandbox command sequence

```bash
# From inside the paper workspace created above
atlas research run --symbol ATLAS-DEMO --json
atlas research list --json
atlas research summary --json
atlas research check-artifacts --json
atlas research timeline --json
atlas research providers --json
```

The `research` commands above use the built-in deterministic local provider. No real LLM/provider call is made.

### Validation commands

```bash
# Verify docs and safety invariants without executing the demo
python3.11 scripts/check_demo_proof.py
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/check_public_docs_consistency.py
python3.11 scripts/check_product_demo_pack.py

# Generate and validate a reviewable evidence bundle
./scripts/demo_product_walkthrough.sh --output-dir /tmp/atlas-evidence --deterministic
python3.11 scripts/check_product_demo_evidence.py /tmp/atlas-evidence

./scripts/release_check.sh --quick
```

### What each command proves and does not prove

| Command | Proves | Does not prove |
|---|---|---|
| `atlas validate` | Paper mode is default; live trading is disabled | Strategy correctness or future performance |
| `atlas doctor --json` | Local safety state is readable without secrets or network | Broker connectivity or live execution readiness |
| `atlas run --mode paper --dry-run` | The paper plan can be printed locally | Provider execution or order submission |
| `atlas backtest run ...` | Deterministic local simulation runs on CSV sample data | Real-market behavior or profitability |
| `atlas research ...` | Local artifact pipeline works with deterministic mock provider | Real LLM/provider execution |

## Demo safety boundary

All default product demos run **paper-only, offline, and without credentials**:

- **No broker** — the demo uses no live broker adapter and does not sync, hold, or submit orders.
- **No network** — the demo runs on the bundled local `data/sample/ohlcv.csv`; no provider, broker, exchange, or remote API calls are made.
- **No credentials** — no API keys, tokens, account IDs, or secrets are loaded, generated, or required.
- **No live trading** — `trading_mode` stays `"paper"`, `enable_live_trading` and `enable_live_submit` remain `false`, and `can_submit` stays `false`.

The canonical demo is `./scripts/demo_product_walkthrough.sh`, which creates a temporary workspace, validates paper mode, runs redacted local diagnostics, prints a paper dry-run, executes a deterministic local backtest on `DEMO-SYMBOL`, verifies local artifacts, and summarizes what remains disabled. Provider execution remains locked and trust remains blocked for the demo path.

This demo is a proof of workflow mechanics, safety-gate behavior, and local audit generation. It is not a live-trading setup, not a production readiness claim, and does not imply profitability or trading correctness.

## Expected output

The demo pack runs locally without credentials, provider calls, broker contact, or live trading. A successful run produces output similar to the following.

### Terminal flow

```bash
python3.11 -m pip install -e .
./scripts/demo_product_walkthrough.sh
```

Expected console output (excerpt):

```text
================================================================================
Atlas Agent — broker-neutral supervised trading workspace
Package/source version: 0.6.11  (v0.6.12 is the planning line)
License: MIT  |  Built by Natan Mucelli
================================================================================
A local-first research and paper-trading workbench with
deterministic safety gates, tamper-evident audit logs, and
sandbox-only provider safety workflows.
Default posture: paper-first, safe-by-default, broker-neutral.
This walkthrough is sandbox/preflight-only. It does not enable
live trading, submit broker orders, execute provider calls, or
load credentials. Provider execution remains locked.
Not financial advice. Trading involves significant risk of loss.
Expected runtime: ~3–6 minutes
================================================================================

Workspace: /tmp/atlas-agent-product-walkthrough.XXXXXX
Symbol: ATLAS-DEMO
Backtest symbol: DEMO-SYMBOL
Guide: docs/product-demo-pack.md

================================================================================
  Section 1: Create a sandbox workspace
================================================================================
  Purpose: Initialize an isolated temporary workspace from the routine-trader template.
  Safety: paper-only; no credentials; no broker/provider calls; no live orders
--------------------------------------------------------------------------------

$ atlas init /tmp/atlas-agent-product-walkthrough.XXXXXX --template routine-trader
Atlas Agent workspace created: ... (template: routine-trader)

$ atlas discipline setup --manual --yes
Discipline profile created at .atlas/discipline.md

$ atlas config set market.symbol ATLAS-DEMO
Updated market.symbol in config.toml

$ atlas validate
...
[✓] Live trading
    Disabled by default.
...
Status: not ready for agentic paper workflows
...

$ atlas run --mode paper --dry-run --symbol ATLAS-DEMO
Atlas Agent Plan
...
Plan: Market open. Paper trade cycle.

$ atlas backtest run --symbol DEMO-SYMBOL --data ...
Backtest complete: DEMO-SYMBOL
...
Report saved to: .atlas/backtests/.../result.json

$ atlas audit verify --all
No manifests found.

Product walkthrough demo complete.
Review the workspace at: /tmp/atlas-agent-product-walkthrough.XXXXXX
This walkthrough was paper-only and local-only: no credentials loaded, no provider calls, no broker contact, and no live orders submitted.
```

Notes:
- `Status: not ready for agentic paper workflows` is expected when no AI provider API key is configured; the demo still completes.
- `No manifests found` is expected because the paper dry-run does not create run manifests.
- The backtest report path includes a timestamp and varies per run.

### Pack-level checks

| Command | Expected result | Exit code |
|---|---|---|
| `./scripts/demo_product_walkthrough.sh` | Workspace created, paper dry-run printed, backtest completed, audit verified | `0` |
| `./scripts/demo_research_workflow.sh` | Research chain artifacts created with `ok: true`; no pending orders | `0` |
| `python3.11 scripts/check_demo_proof.py` | `Demo proof check PASSED` | `0` |
| `python3.11 scripts/check_product_demo_pack.py` | `Product demo and marketplace readiness check PASSED` | `0` |
| `./scripts/release_check.sh --quick` | Quick release gate reports success | `0` |

### Generated artifacts

- Temporary demo workspace under `/tmp/atlas-agent-product-walkthrough.XXXXXX` (or `$DEMO_WORKSPACE`).
- `.atlas/config.toml` with `market.symbol = "ATLAS-DEMO"` and paper mode.
- `.atlas/discipline.md` default safe discipline profile.
- `.atlas/backtests/bt-<timestamp>/result.json` and `report.md` from sample-data backtest.
- Research artifacts from `atlas research run/plan/verify/evaluate/...` when the research demo is run.
- Empty `pending_orders/` and `audit/` directories (no orders created in default demo).

See [Demo Artifact Index](demo-artifact-index.md) for a complete indexed view of each artifact, its purpose, and the safety invariant it demonstrates.

## Product demo evidence bundle

For reviewer-facing, deterministic proof that the demo ran in paper/dry-run mode without credentials, provider calls, broker contact, or network access, use the optional evidence bundle:

```bash
./scripts/demo_product_walkthrough.sh --output-dir /tmp/atlas-evidence --deterministic
python3.11 scripts/check_product_demo_evidence.py /tmp/atlas-evidence
```

The bundle includes `evidence.json`, `summary.md`, `safety-boundaries.md`, `artifacts-index.md`, `commands.txt`, captured command outputs, copied workspace artifacts, and `checksums.sha256`. See [Product Demo Evidence](product-demo-evidence.md) for the full contract.

### Success criteria

- All demo scripts and checks exit with code `0`.
- No broker credentials, provider API keys, or `.env.atlas` secrets are required.
- No live orders are submitted.
- No provider or broker network calls are made.
- No pending orders are created.

### Common failures

| Symptom | Likely cause | Resolution |
|---|---|---|
| `Missing prerequisite: sample data not found` | `data/sample/ohlcv.csv` is missing | Clone repo and ensure sample data is present |
| `atlas: command not found` | Atlas not installed in editable mode | Run `python3.11 -m pip install -e .` |
| `Status: not ready for agentic paper workflows` | No AI provider configured | Expected and safe; backtest/dry-run still complete |
| `No manifests found` | Dry-run does not create manifests | Expected and safe |

## Safety note

This demo pack is **paper-first, sandbox-only, and preflight-only**. It is meant to run locally with no broker credentials, no provider API keys, and no network calls.

By default Atlas keeps:

- `trading_mode = "paper"`
- `broker.enable_live_trading = false`
- `broker.enable_live_submit = false`
- provider execution locked
- broker order submission blocked by `can_submit=false`
- leverage disabled

Nothing in this pack submits live orders, calls providers, enables live trading, approves orders, or loads credentials. It demonstrates workflow mechanics and local safety boundaries only. For the safe configuration details see [Paper-Trading Guide](paper-trading-guide.md) and [Broker and Provider Preflight Diagnostics](preflight-diagnostics.md).

## 5-minute reviewer walkthrough

Use this flow when showing Atlas to someone who has never seen the repo.

| Step | Time | What to run | What it proves |
|---|---|---|---|
| 1. Install & inspect | ~1 min | `python3.11 -m pip install -e .`<br>`atlas --help`<br>`atlas validate` | Atlas installs cleanly and reports paper mode by default. |
| 2. Create a paper workspace | ~1 min | `atlas init /tmp/atlas-demo.XXXX --template routine-trader`<br>`cd /tmp/atlas-demo.XXXX`<br>`atlas discipline setup --manual --yes`<br>`atlas config set market.symbol ATLAS-DEMO` | Workspace creation, safe discipline profile, and explicit symbol choice. |
| 3. Confirm safe defaults | ~1 min | `atlas validate`<br>`atlas doctor --json` | Live trading is disabled, no broker credentials are loaded, and execution stays blocked. |
| 4. Run paper dry-run + backtest | ~1 min | `atlas run --mode paper --dry-run --symbol ATLAS-DEMO`<br>`atlas backtest run --data data/sample/ohlcv.csv --symbol DEMO-SYMBOL` | The planned paper workflow prints without broker contact, and the deterministic local backtest produces reports. |
| 5. Inspect local artifacts | ~1 min | `ls .atlas/backtests/`<br>`atlas audit verify --all`<br>`atlas backtest runs --validate --json` | Local evidence is created; the audit queue and pending-orders folders remain empty. |

### What to point out during the demo

- **No credentials required** — the demo never loads `.env.atlas` or broker API keys.
- **Live trading disabled** — `atlas validate` and `atlas doctor` confirm this.
- **Provider execution remains locked** — no LLM/provider calls are made; the default research provider is local/deterministic.
- **Risk gates are deterministic** — see [Demo: Risk Rejection](demo-risk-rejection.md) for a follow-on demo of `RiskManager` blocking an unsafe order.
- **Backtest is local simulation** — historical/sample results do not guarantee future performance.

## Related docs and scripts

- [Paper-Trading Guide](paper-trading-guide.md) — manual setup and annotated fail-closed configuration.
- [Demo: Paper Workflow](demo-paper-workflow.md) — expected output and common failures.
- [Demo Artifact Index](demo-artifact-index.md) — what files the demo creates and what each proves.
- [External Reviewer Walkthrough](external-reviewer-walkthrough.md) — 10–15 minute safe review path.
- [Reviewer Golden-Path Validation Guide](reviewer-golden-path.md) — canonical command sequence.
- [Reviewer Checklist](reviewer-checklist.md) — structured checklist before trusting or recommending.
- [Public Launch Readiness](public-launch-readiness.md) — verified checks and disabled-by-default state.
- [Public Launch Messaging](public-launch-messaging.md) — safe, copy-pasteable messaging drafts.
- [Feedback Request Guide](feedback-request-guide.md) — how to ask for technical feedback safely.
- [Marketplace Listing](marketplace-listing.md) — safe, copy-pasteable public listing.
- [Autonomy Roadmap](autonomy-roadmap.md) — bounded autonomy levels from research to supervised live suggestions.
- [Product Demo Evidence](product-demo-evidence.md) — deterministic evidence bundle contract and reviewer guide.
- [scripts/demo_product_walkthrough.sh](../scripts/demo_product_walkthrough.sh) — one-command product walkthrough (canonical demo for this pack).
- [scripts/demo_paper_workflow.sh](../scripts/demo_paper_workflow.sh) — legacy one-command paper workflow.
- [scripts/check_product_demo_pack.py](../scripts/check_product_demo_pack.py) — deterministic static checker for this pack.
