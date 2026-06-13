# Reviewer Golden-Path Validation Guide

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

This guide is the fastest safe path for an external reviewer to verify the current Atlas Agent state.

## Quick validation path

After cloning and installing (`python3.11 -m pip install -e .`), run these commands in order to verify the current `v0.6.10` public release and `v0.6.11` planning state:

```bash
# Release metadata and version consistency
python3.11 scripts/check_release_metadata.py
python3.11 scripts/check_version_consistency.py

# Trust center and public docs consistency
python3.11 scripts/check_trust_center.py
python3.11 scripts/check_public_docs_consistency.py

# Backtest report schema and v0.6.11 planning baseline
python3.11 scripts/check_backtest_report_schema.py
python3.11 scripts/check_v0611_planning.py

# Local gates
./scripts/dev_check.sh
./scripts/ci_check.sh
./scripts/release_check.sh --quick
```

Optional reviewer CLI checks:

```bash
atlas validate
atlas backtest runs --validate --json
```

For a safe paper demo, see the [Paper Workflow Demo](demo-paper-workflow.md) or run `./scripts/demo_paper_workflow.sh`.

All commands above are local, deterministic, and require no credentials, providers, brokers, or network access.

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

## How to run it

From the repository root:

```bash
# Text output (default)
python3.11 scripts/smoke_reviewer_golden_path.py

# JSON output
python3.11 scripts/smoke_reviewer_golden_path.py --json

# Keep the temporary workspace for inspection
python3.11 scripts/smoke_reviewer_golden_path.py --keep-temp

# Skip the release_check.sh --quick step for faster iteration
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
