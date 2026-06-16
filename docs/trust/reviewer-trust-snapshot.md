# Atlas Agent Reviewer Trust Snapshot

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## What is the reviewer trust snapshot?

The reviewer trust snapshot is a **local, offline, deterministic artifact** produced by [`scripts/build_reviewer_trust_snapshot.py`](../../scripts/build_reviewer_trust_snapshot.py). It gives reviewers, founders, and marketplace operators a one-page Markdown summary plus a machine-readable JSON file that proves the project's current release identity, disabled-by-default safety posture, CI evidence references, and demo evidence checksum.

The snapshot is intentionally small and self-contained so it can be handed to an external reviewer without exposing credentials, broker details, provider API keys, or private financial data.

## What it proves

- Current source/package version and public release identity.
- Next planned release line.
- Whether PyPI was published (it was not).
- Whether a GitHub release/tag exists for the current public release.
- CI run IDs supplied by the builder.
- A deterministic checksum reference for a CAND-002 product demo evidence bundle.
- All required safety invariants are set to their expected values:
  - `live_trading_disabled_by_default: true`
  - `live_submit_disabled_by_default: true`
  - `provider_execution_disabled_by_default: true`
  - `broker_execution_disabled_by_default: true`
  - `credentials_required_for_demo: false`
  - `network_required_for_demo: false`
  - `autonomous_trading_claimed: false`
  - `profit_claims_absent: true`
  - `no_risk_claims_absent: true`

## What it does not prove

- It does not prove profitability, strategy correctness, or future performance.
- It does not prove production readiness or suitability for live trading.
- It does not prove real-market behavior, broker connectivity, or provider reliability.
- CI run IDs are provided by the operator at build time and are not independently verified against GitHub.

## Build a snapshot

```bash
python3.11 -m pip install -e .
python3.11 scripts/build_reviewer_trust_snapshot.py --output-dir ./artifacts/trust-snapshot
```

Use `--deterministic` to produce stable timestamps and sorted output for tests:

```bash
python3.11 scripts/build_reviewer_trust_snapshot.py \
  --output-dir ./artifacts/trust-snapshot \
  --deterministic
```

### Pass CI run IDs

```bash
python3.11 scripts/build_reviewer_trust_snapshot.py \
  --output-dir ./artifacts/trust-snapshot \
  --ci-run-id 27578051644 \
  --research-ci-run-id 27577320648
```

`--ci-run-id` may be repeated if multiple main CI runs are relevant.

### Link a CAND-002 evidence bundle

```bash
python3.11 scripts/build_reviewer_trust_snapshot.py \
  --output-dir ./artifacts/trust-snapshot \
  --evidence-bundle ./artifacts/product_demo/my-evidence \
  --ci-run-id 27578051644 \
  --research-ci-run-id 27577320648
```

The builder computes a stable SHA-256 checksum over the bundle contents and records it in `reviewer-trust-snapshot.json` and `reviewer-trust-snapshot.md`.

## Validate a snapshot

```bash
python3.11 scripts/check_reviewer_trust_snapshot.py ./artifacts/trust-snapshot
```

JSON output:

```bash
python3.11 scripts/check_reviewer_trust_snapshot.py ./artifacts/trust-snapshot --json
```

Self-test mode (builds a deterministic temp snapshot and validates it):

```bash
python3.11 scripts/check_reviewer_trust_snapshot.py --self-test
```

The checker fails closed if any of the following are true:

- A required file is missing.
- `reviewer-trust-snapshot.json` has an unsafe value such as `live_trading_disabled_by_default: false`.
- `pypi_published` is not `false`.
- Required Markdown sections or safety phrases are missing.
- A secret-like pattern or forbidden marketing claim appears in any snapshot file.
- A recorded checksum does not match the file.

## Snapshot contents

| File | Purpose |
|---|---|
| `reviewer-trust-snapshot.json` | Machine-readable snapshot schema with release identity, safety invariants, capability status, and checksums. |
| `reviewer-trust-snapshot.md` | One-page human-readable summary for reviewers and marketplace operators. |
| `checksums.sha256` | SHA-256 checksums of every file in the snapshot (except this file). |

## JSON schema

Key fields (all required):

| Field | Expected value | Meaning |
|---|---|---|
| `schema_version` | `"atlas-reviewer-trust-snapshot/1.0"` | Snapshot schema version. |
| `generated_at` | ISO-8601 timestamp or deterministic placeholder | When the snapshot was produced. |
| `repository` | `"usernotfinded/atlas-agent"` | Repository identifier. |
| `source_version` | e.g. `"0.6.11"` | Current source/package version. |
| `current_public_release` | e.g. `"v0.6.11"` | Current public GitHub release. |
| `next_planned_release` | e.g. `"v0.6.12"` | Next planned release line. |
| `pypi_published` | `false` | PyPI publication status. |
| `release_status` | human-readable string | Summary of release/tag/PyPI state. |
| `ci_runs` | object | Supplied CI run IDs and explanatory note. |
| `evidence_bundle` | object or `null` | Evidence bundle path, checksum, and file count. |
| `safety_invariants` | object of booleans | All values must match expected. |
| `capability_status` | object of strings | Default state of key capabilities. |
| `forbidden_claims_absent` | object of booleans | All values must be `true`. |
| `generated_files` | object | Relative paths of generated files. |
| `checksums` | object | SHA-256 of generated files. |

## Safety and scope

The builder and checker are:

- **Local-only**: no network calls.
- **Credential-free**: no API keys, broker credentials, or secrets loaded.
- **Read-only**: no broker orders, provider calls, or live trading enabled.
- **Deterministic**: `--deterministic` produces stable output for tests and diffs.

## Run the manual GitHub Actions workflow

A maintainer can also build the snapshot through a manual, read-only GitHub Actions workflow:

1. Go to **Actions → Reviewer Trust Snapshot** in the repository.
2. Click **Run workflow**.
3. Optionally provide:
   - `main_ci_run_id` — a main CI run ID to reference.
   - `research_ci_run_id` — a Research CI run ID to reference.
   - `evidence_bundle_path` — a path to a generated CAND-002 evidence bundle (rarely available in CI; leave empty to omit).
   - `deterministic` — enable to produce stable timestamps and redacted paths.
4. The workflow builds the snapshot, validates it with `scripts/check_reviewer_trust_snapshot.py`, and uploads `reviewer-trust-snapshot` as a GitHub Actions artifact.

The workflow does not create tags, releases, or PyPI packages. It does not enable live trading, provider execution, broker execution, or order submission. It requires no secrets or credentials.

## Include in a release assurance pack

The reviewer trust snapshot can optionally be bundled into the local release
assurance output. This is off by default and must be requested explicitly.

```bash
python scripts/release_assurance.py \
  --version v0.6.11 \
  --output artifacts/release_assurance/v0.6.11-local \
  --include-reviewer-trust-snapshot
```

With the flag, `scripts/release_assurance.py` writes a deterministic snapshot to
`<output>/reviewer-trust-snapshot/` and validates it with
`scripts/check_reviewer_trust_snapshot.py`. If validation fails, the assurance
pack exits non-zero.

This integration is local-only. It does not create tags or GitHub releases, does
not publish to PyPI, does not call providers or brokers, and does not enable live
trading. It also does not prove profitability, production readiness, or
suitability for live trading.

The manual Release Assurance workflow supports the same opt-in through the
`include_reviewer_trust_snapshot` input (default `false`). See
[`.github/workflows/release-assurance.yml`](../../.github/workflows/release-assurance.yml).

## Validate the integration locally

```bash
python3.11 scripts/check_release_assurance_snapshot_integration.py
python3.11 -m pytest tests/test_release_assurance_snapshot_integration.py -q
```

## Validate the workflow file locally

```bash
python3.11 scripts/check_reviewer_trust_snapshot_workflow.py
python3.11 -m pytest tests/test_reviewer_trust_snapshot_workflow.py -q
```

## Related docs, scripts, and workflows

- [Product Demo Evidence Bundle](../product-demo-evidence.md) — CAND-002 evidence bundle.
- [Product Demo and Marketplace Readiness Pack](../product-demo-pack.md) — CAND-001 overview.
- [Atlas Agent Trust Center](README.md) — trust center entry point.
- [Trust and Release Status](v0.6.11-status.md) — current public release status.
- [Reviewer Trust Snapshot GitHub Actions Workflow](../../.github/workflows/reviewer-trust-snapshot.yml) — manual workflow.
