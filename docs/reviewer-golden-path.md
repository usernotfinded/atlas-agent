# Reviewer Golden-Path Validation Guide

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

This is the canonical reviewer entry point for verifying the current Atlas
Agent state. Other reviewer and demo documents link here instead of repeating
their own command sequences.

## Canonical reviewer flow

From the repository root:

```bash
python3.11 -m pip install -e .
python3.11 scripts/smoke_reviewer_golden_path.py
./scripts/demo_paper_workflow.sh
```

The smoke script creates an isolated temporary workspace and exercises the
safe local CLI path. The paper demo creates a separate temporary workspace and
shows validation, redacted diagnostics, a paper dry-run, and a deterministic
sample-data backtest. Neither command requires credentials or network access.

For manual paper setup, use the [Paper-Trading Guide](paper-trading-guide.md).
For the `atlas doctor` field contract, use
[Broker and Provider Preflight Diagnostics](preflight-diagnostics.md). Expected
demo output is documented in [Demo: Paper Workflow](demo-paper-workflow.md),
and generated files are mapped in the
[Demo Artifact Index](demo-artifact-index.md).

## Release and documentation assurance

Run these checks after the canonical flow to verify the current `v0.6.10`
public release and `v0.6.11` planning state:

```bash
python3.11 scripts/check_release_metadata.py
python3.11 scripts/check_version_consistency.py
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/check_trust_center.py
python3.11 scripts/check_public_docs_consistency.py
python3.11 scripts/check_public_launch_readiness.py
python3.11 scripts/check_reviewer_onboarding.py
python3.11 scripts/check_backtest_report_schema.py
python3.11 scripts/check_v0611_planning.py
python3.11 scripts/check_demo_proof.py
./scripts/release_check.sh --quick
```

All commands above are local and deterministic. They do not authorize provider
execution, contact brokers, submit orders, or enable live trading.

## What this verifies

The reviewer golden-path smoke test validates that a new external reviewer can:

1. Clone the repository.
2. Install the package locally (editable or otherwise).
3. Create a temporary workspace from the built-in `routine-trader` template.
4. Run the main safe CLI workflow without credentials, providers, brokers, or network access.

It exercises the following commands in order:

```bash
atlas --help
atlas init <temp_workspace> --template routine-trader
atlas discipline setup --manual --yes
atlas config set market.symbol DEMO-SYMBOL
atlas validate
atlas backtest run --data data/sample/ohlcv.csv --symbol DEMO-SYMBOL --json
atlas research run --symbol DEMO-SYMBOL --json
atlas research summary --json
atlas memory doctor --json
atlas events doctor
```

All of these commands are local-only and deterministic. No API keys, `.env` files, or broker credentials are required.

## What this does not verify

- **Trading safety.** This is a smoke test, not a proof that risk gates, kill switches, or approval flows work correctly under all conditions.
- **Provider execution.** The `research run` command uses the built-in `deterministic` provider, which is a local mock. It does not exercise real AI providers.
- **Broker execution.** No broker is contacted; no orders are submitted.
- **Live trading.** Live trading remains disabled by default. This test never enables it.
- **Network resilience.** The test does not call external endpoints.

## Smoke script options

From the repository root:

```bash
# Text output (default)
python3.11 scripts/smoke_reviewer_golden_path.py

# JSON output
python3.11 scripts/smoke_reviewer_golden_path.py --json

# Keep the temporary workspace for inspection
python3.11 scripts/smoke_reviewer_golden_path.py --keep-temp

# Skip release_check.sh --quick for focused local iteration
python3.11 scripts/smoke_reviewer_golden_path.py --skip-release-check
```

The script creates a temporary workspace under `$TMPDIR` (or `/tmp`), runs the commands, and cleans up afterward unless `--keep-temp` is passed.

## Exit codes

- `0` — all smoke steps passed.
- `2` — one or more steps failed.

## Environment variables

- `PYTHON_BIN` — Python interpreter to use (default: `python3.11`).
- `DEMO_SYMBOL` — symbol used for backtest and research (default: `DEMO-SYMBOL`).
- `PYTHONPATH` — automatically set to `src/` so the local package is used.

## Safety assertions

- The smoke test runs in a temporary workspace outside the repository.
- It does not call providers, brokers, or network endpoints.
- It does not load credentials or require `.env.atlas`.
- It does not submit orders or enable live trading.
- It does not mutate the repository.
- Live trading is disabled by default.
- Provider execution remains locked.
- Trust remains blocked.
