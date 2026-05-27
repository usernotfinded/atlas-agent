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

## 10–15 minute review path

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

### Expected safe failures

- `atlas validate` may report missing provider API keys. This is expected and safe — Atlas does not require real credentials for paper and backtest workflows.
- `atlas research provider-safety-dossier-latest` may return `found: false` if no dossier exists. This is safe.
- `scripts/check_package_distribution.py` may skip the twine check if `twine` is not installed. This is safe.

## What to inspect in the repo

1. README.md — "What this is" and "What this is not" sections
2. SECURITY.md — security policy and reporting path
3. CONTRIBUTING.md — safety boundaries for contributors
4. docs/public-launch-readiness.md — verified checks and disabled features
5. docs/reviewer-checklist.md — structured checklist for review
6. docs/provider-safety-dossier.md — sandbox-only safety workflow
7. src/atlas_agent/brokers/ — broker adapter boundaries
8. src/atlas_agent/risk/ — deterministic risk gate implementations
9. src/atlas_agent/safety/ — safety invariants and kill switch

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
