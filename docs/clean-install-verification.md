# Clean Install Verification

> **Not financial advice.** This is a release-engineering check, not a trading recommendation.

The `scripts/check_clean_install.py` script verifies that a fresh user can install Atlas Agent from the current worktree without credentials, network calls, or live-trading enablement.

## What it checks

1. **No-network editable install** — `pip install --no-index --no-build-isolation -e .` succeeds in a temporary virtual environment. PyPI is not contacted by default.
2. **Installed console entrypoint** — The `atlas` console script installed in the venv responds to `atlas --help` and `atlas validate`. It does not use `python -m atlas_agent.cli` as a substitute.
3. **Validate safe** — `atlas validate` fails safely (reports missing workspace/config, does not crash, does not enable live trading).
4. **Version match** — Installed package version matches the expected PEP 440 version.
5. **No absolute paths** — Captured output does not leak local paths. Temp paths, repo paths, home paths, and system paths are redacted before printing.
6. **README quickstart** — Delegates to `scripts/verify_readme_quickstart.py` if available.

## What it does NOT do

- Does not access PyPI or any network by default.
- Does not clone from network.
- Does not call provider APIs.
- Does not call broker APIs.
- Does not load credentials.
- Does not submit orders.
- Does not enable live trading.
- Does not publish packages.

## Usage

```bash
# Default: no-network clean install in temp venv
python3.11 scripts/check_clean_install.py

# Plan mode: show steps without creating files
python3.11 scripts/check_clean_install.py --dry-run

# Allow network (only if local build deps are missing)
python3.11 scripts/check_clean_install.py --allow-network

# Skip venv creation in plan mode only (dry-run)
python3.11 scripts/check_clean_install.py --dry-run --skip-venv

# Keep temp directory for debugging
python3.11 scripts/check_clean_install.py --keep-temp
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Clean install verification passed |
| 1 | Argument or setup error |
| 2 | Verification failure |

## Safety posture

- Sandbox/paper/preflight only.
- Live trading disabled by default.
- Provider execution remains locked.
- Trust remains blocked.
- No broker/order path.
- No credentials required.
- Not financial advice. Does not imply profitability or trading correctness.
