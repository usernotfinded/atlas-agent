# External Reviewer Walkthrough

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## Who this walkthrough is for

This walkthrough is for external technical reviewers who want to evaluate Atlas Agent safely and quickly without credentials, providers, brokers, or live trading.

## What Atlas Agent is

Atlas Agent is a **local-first sandbox/paper trading research workbench** with deterministic safety gates, audit logs, and provider-neutral analysis tools. It is designed as a broker-neutral supervised workspace above user-selected models, broker/API providers, credentials, and risk limits.

## What Atlas Agent is not

- **Not a live trading system by default.** Live trading is disabled by default and requires explicit multi-factor opt-in.
- **Does not imply profitable outcomes.** Atlas does not predict profit, guarantee returns, or claim future performance.
- **Not a broker.** Atlas is broker-neutral and does not custody funds.
- **Not a licensed financial advisor.** This is software, not financial advice.
- **Not autonomous.** All live actions require explicit human confirmation when enabled.

## Canonical reviewer demo path

The recommended path to review the paper demo is:

1. Install Atlas (this page).
2. Run the paper demo or inspect the safe command list.
3. Read expected output in [Demo: Paper Workflow](demo-paper-workflow.md).
4. Inspect the [Demo Artifact Index](demo-artifact-index.md) for artifact details.
5. Run the deterministic [Demo Proof Checker](../scripts/check_demo_proof.py) to validate docs and safety invariants without executing the demo.
6. Run the lightweight [Demo Command Smoke Checker](../scripts/check_demo_command_smoke.py) to validate that the demo script surface remains intact in the fastest local gates.

These commands run locally without credentials, network calls, or live trading.

### Install / local setup

```bash
python3.11 -m pip install -e .
```

### Safe commands to run

```bash
# Version consistency
python3.11 scripts/check_version_consistency.py

# Forbidden claims scan
python3.11 scripts/check_forbidden_claims.py

# Public docs consistency
python3.11 scripts/check_public_docs_consistency.py

# Public launch readiness
python3.11 scripts/check_public_launch_readiness.py

# Reviewer onboarding check
python3.11 scripts/check_reviewer_onboarding.py

# Clean install dry-run
python3.11 scripts/check_clean_install.py --dry-run

# Package distribution dry-run
python3.11 scripts/check_package_distribution.py --dry-run

# Quick release gate
./scripts/release_check.sh --quick

# Backtest report schema validation
python3.11 scripts/check_backtest_report_schema.py

# List backtest runs with schema validation
atlas backtest runs --validate --json
```

### Optional longer commands

These may take several minutes:

```bash
# Full clean install verification
python3.11 scripts/check_clean_install.py

# Full package distribution verification
python3.11 scripts/check_package_distribution.py

# Research gate (research tests + demo)
./scripts/release_check.sh --research

# Full release gate (all tests + demos)
./scripts/release_check.sh --full
```

### Paper workflow demo

Run the reproducible demo script to see a full paper-mode workflow:

```bash
./scripts/demo_paper_workflow.sh
```

**What to expect:**
- A temporary workspace is created.
- A safe discipline profile and demo symbol are configured.
- `atlas validate` confirms the workspace is paper-only.
- A paper dry-run prints the planned workflow without sending orders.
- A deterministic sample-data backtest runs and writes a local report.
- The script exits `0` with no credentials required.

**How to know it worked:**
- The final line reads `Demo complete. Review the temporary workspace at: ...`
- No provider API keys or broker credentials were requested.
- `atlas validate` reports `Live trading: Disabled by default`.

For full expected output, success criteria, and artifact locations, see [Demo: Paper Workflow](demo-paper-workflow.md).
For an indexed view of every demo artifact and the safety invariant it demonstrates, see [Demo Artifact Index](demo-artifact-index.md).

### Expected safe failures

- `atlas validate` may report missing provider API keys. This is expected and safe — Atlas does not require real credentials for paper and backtest workflows.
- `atlas research provider-safety-dossier-latest` may return `found: false` if no dossier exists. This is safe.
- `scripts/check_package_distribution.py` may skip the twine check if `twine` is not installed. This is safe.

## What to inspect in the repo

1. README.md — "What this is" and "What this is not" sections
1. SECURITY.md — security policy and reporting path
1. CONTRIBUTING.md — safety boundaries for contributors
1. docs/public-launch-readiness.md — verified checks and disabled features
1. docs/reviewer-checklist.md — structured checklist for review
1. docs/public-faq.md — answers to common questions
1. docs/feedback-request-guide.md — how to ask for feedback safely
1. docs/provider-safety-dossier.md — sandbox-only safety workflow
1. src/atlas_agent/brokers/ — broker adapter boundaries
1. src/atlas_agent/risk/ — deterministic risk gate implementations
1. src/atlas_agent/safety/ — safety invariants and kill switch

## Safety boundaries to verify

Run these commands to confirm protected boundaries are clean:

```bash
git diff -- src/atlas_agent/config src/atlas_agent/brokers src/atlas_agent/execution src/atlas_agent/safety src/atlas_agent/risk
git diff --cached -- src/atlas_agent/config src/atlas_agent/brokers src/atlas_agent/execution src/atlas_agent/safety src/atlas_agent/risk
```

Expected: no output.

## What should remain disabled

- **Live trading disabled by default** — requires explicit multi-factor opt-in.
- **Provider execution remains locked** — no real LLM/provider calls are made by default.
- **Broker order submission** is blocked by `can_submit=false`.
- **Credentials** are not loaded unless explicitly configured. No credentials required for default verification.
- **Trust remains blocked** — mock responses in safety workflows are explicitly not trusted.

## Validation

Run the deterministic demo proof checker to verify documentation and safety invariants without executing the demo:

```bash
python3.11 scripts/check_demo_proof.py
```

## How to report findings

- Security or safety issues: [GitHub Security Advisories](https://github.com/usernotfinded/atlas-agent/security/advisories)
- Bugs: use the bug report issue template
- Documentation issues: use the docs issue template
- General feedback: use the feature request template or open a discussion

## What not to assume

- Do not assume Atlas is appropriate for trading real money.
- Do not assume historical backtest results predict future performance.
- Do not assume provider execution is enabled or trustworthy.
- Do not assume the presence of broker adapters implies live trading readiness.
- Do not assume this is financial advice.
