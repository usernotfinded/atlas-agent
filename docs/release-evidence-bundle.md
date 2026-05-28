# Release Evidence Bundle

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## What this is

The release evidence bundle is a deterministic, local-only report that consolidates version, git, safety, and check-command evidence into a single JSON and Markdown artifact. It is intended for reviewers and release managers who need a snapshot of repository health before tagging or recommending the project.

## What it verifies

- **Package version consistency** between `pyproject.toml` and `src/atlas_agent/__init__.py`
- **Git state**: current branch, commit, working tree cleanliness, diff-check cleanliness
- **Changes since the last stable tag** (`v0.5.7`)
- **Protected boundary status**: whether `config`, `brokers`, `execution`, `safety`, or `risk` directories changed since the stable tag
- **Check command results**:
  - `check_version_consistency.py`
  - `check_forbidden_claims.py`
  - `check_public_docs_consistency.py`
  - `check_public_launch_readiness.py`
  - `check_stable_release_decision.py`
  - `check_cli_command_compatibility.py`
  - `smoke_reviewer_golden_path.py` (unless `--skip-slow`)
  - `release_check.sh --quick` (only with `--include-quick-check`)

## What it does not verify

- **Trading safety.** This is an evidence snapshot, not a proof that risk gates, kill switches, or approval flows are correct under all conditions.
- **Provider execution.** No provider is called.
- **Broker execution.** No broker is contacted.
- **Live trading.** Live trading remains disabled by default; this bundle never enables it.
- **Network resilience.** No external endpoints are called.
- **Profitability or correctness.** The bundle makes no claims about strategy performance.

## How to run it

From the repository root:

```bash
# Default: generate JSON and Markdown under artifacts/release_evidence/
python3.11 scripts/build_release_evidence_bundle.py

# Emit JSON to stdout as well
python3.11 scripts/build_release_evidence_bundle.py --json

# Skip slow checks (e.g. reviewer golden-path smoke)
python3.11 scripts/build_release_evidence_bundle.py --skip-slow

# Also include release_check.sh --quick (slow)
python3.11 scripts/build_release_evidence_bundle.py --include-quick-check

# Custom output directory
python3.11 scripts/build_release_evidence_bundle.py --output-dir /tmp/atlas-evidence
```

## Output artifacts

After running, two files are written to `artifacts/release_evidence/` (or the directory specified by `--output-dir`):

- `evidence.json` — structured, machine-readable report
- `evidence.md` — human-readable report for reviewers

## JSON shape

```json
{
  "passed": true,
  "generated_at": "...",
  "package_version": "0.5.8.dev0",
  "public_stable_tag": "v0.5.7",
  "current_branch": "main",
  "current_commit": "...",
  "working_tree_clean": true,
  "diff_check_clean": true,
  "changed_since_v0_5_7": ["M\tfile.py", ...],
  "protected_boundaries_clean": true,
  "protected_boundaries": {
    "src/atlas_agent/config": [],
    "src/atlas_agent/brokers": [],
    "src/atlas_agent/execution": [],
    "src/atlas_agent/safety": [],
    "src/atlas_agent/risk": []
  },
  "checks": [
    {
      "name": "check_version_consistency",
      "command": ["python3.11", "scripts/check_version_consistency.py"],
      "exit_code": 0,
      "passed": true,
      "stdout_redacted": "...",
      "stderr_redacted": "..."
    }
  ],
  "safety_summary": {
    "provider_execution_enabled": false,
    "broker_execution_enabled": false,
    "live_trading_enabled_by_default": false,
    "credentials_loaded": false,
    "network_calls_required": false
  }
}
```

## Exit codes

- `0` — all required evidence checks passed and `git diff --check` is clean.
- `2` — one or more checks failed, or `git diff --check` reported issues.

## Safety assertions

- The bundle generator is local-only and does not call providers, brokers, or network endpoints.
- It does not load credentials or require `.env.atlas`.
- It does not submit orders or enable live trading.
- It only writes artifacts under `artifacts/release_evidence/` (or the specified output directory).
