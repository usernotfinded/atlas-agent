# Release Candidate Readiness Report

> **Not financial advice.** This document describes a local verification workflow, not trading recommendations.

## What this is

The Release Candidate Readiness Report is a **local, read-only** summary that checks whether the current Atlas Agent repository is ready to be presented as a **sandbox/paper/preflight release candidate**.

It does **not** claim the project is live-trading ready. It does **not** unlock provider execution, broker access, or live trading. It does **not** load credentials or make network calls.

## What it checks

The report inspects repository files and verification scripts to confirm:

- **Version consistency** — `pyproject.toml` matches `src/atlas_agent/__init__.py`.
- **README quickstart verification** — `scripts/verify_readme_quickstart.py` exists.
- **Public docs consistency** — `scripts/check_public_docs_consistency.py` exists.
- **Provider safety dossier documentation** — `docs/provider-safety-dossier.md` and example workflow exist.
- **Provider safety dossier commands documented** — latest, list, and export commands are documented.
- **Release checklist present** — `docs/release-checklist.md` exists.
- **Release note present** — `docs/releases/v0.5.7-rc1.md` exists.
- **Forbidden claims scan clean** — `scripts/check_forbidden_claims.py` passes.
- **Protected boundaries clean** — no diffs in `src/atlas_agent/config`, `brokers`, `execution`, `safety`, `risk`.
- **README safety wording** — sandbox-only, paper-first, offline-safe, live trading disabled by default, not financial advice, profitability limitation.

## What it does not mean

- **Not live trading ready.** The report is about documentation and verification hygiene, not trading execution.
- **Not production trading safe.** Sandbox release candidate status does not imply production safety.
- **Not a trading profitability claim.** The `readiness_score` measures documentation and script coverage, not strategy performance.
- **Not a provider execution unlock.** Provider execution remains locked; the report does not enable it.
- **Not a broker enablement.** Broker order submission remains blocked.
- **Not a trust grant.** Trust remains blocked.

## Safety invariants (hard-false)

The report enforces these invariants as `false`:

- `provider_call_allowed`
- `actual_provider_call_made`
- `provider_response_trusted`
- `mock_response_trusted`
- `trading_signal_generated`
- `approval_created`
- `pending_order_created`
- `broker_touched`
- `network_enabled`
- `credentials_loaded`
- `trust_upgrade_performed`
- `trust_decision_granted`
- `provider_execution_unlocked`
- `real_provider_response_imported`
- `live_trading_path_enabled`
- `broker_order_path_enabled`

If any of these is found to be `true` during validation, the artifact is rejected.

## How to generate it

Inside an Atlas workspace:

```bash
atlas research release-candidate-readiness --symbol ATLAS-DEMO --json
```

This creates an artifact under `.atlas/research/ATLAS-DEMO/release_candidate_readiness_reports/`.

## How to validate it

```bash
atlas research release-candidate-readiness-validate <REPORT_ID> --json
```

Validation checks:
- artifact type and schema version
- hard-false invariants
- unsafe positive claims
- forbidden fragments
- hash integrity
- safe readiness status values

## How to list/show/summarize/doctor

```bash
atlas research release-candidate-readiness-list --json
atlas research release-candidate-readiness-show <REPORT_ID> --json
atlas research release-candidate-readiness-summary <REPORT_ID> --json
atlas research release-candidate-readiness-doctor <REPORT_ID> --json
```

## Version-specific candidate readiness

- [v0.6.13 Candidate Selection](releases/v0.6.13-candidate-selection.md) —
  planning-only candidate-selection gate for the v0.6.13 line.
- [v0.6.12 Candidate Readiness](releases/v0.6.12-candidate-readiness.md) —
  historical release-candidate readiness consolidation for the v0.6.12 planning
  line. The canonical released-state evidence is
  [v0.6.12 Post-Release Evidence](releases/v0.6.12-post-release-evidence.md).

## Limitations

- The report is **repository-local** and **read-only**.
- It does not run the full test suite (`release_check.sh --full`) inside the command; it records whether required scripts exist.
- It does not verify that CI passes or that the package builds on all platforms.
- It does not check broker credentials or provider API keys.
- It does not predict trading performance or strategy correctness.
- Safety validation does not imply profitability or trading correctness.
