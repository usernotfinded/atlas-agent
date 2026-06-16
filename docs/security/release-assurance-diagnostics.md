# Release Assurance Diagnostics

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

`scripts/release_assurance.py` prints a human-readable diagnostic block to `stderr` when a release-assurance check fails. It can also write a machine-readable diagnostics JSON file when invoked with `--diagnostics-json <path>`.

These diagnostics are designed to help maintainers and reviewers understand *why* a check failed without exposing secrets, credentials, or account identifiers.

## What diagnostics are emitted

When `release_assurance.py` detects a failure, it emits a block like the following to `stderr`:

```text
=== Release Assurance Diagnostic ===
Release: v0.6.11
Output directory: artifacts/release_assurance/v0.6.11-local-check
Failed check: github_release_present
Command/function: gh release view v0.6.11 --json url
Exit code: 1
Stderr excerpt:
HTTP 404: Not Found (https://api.github.com/repos/...)
Remediation: Create a GitHub release for v0.6.11 or verify GH_TOKEN is set and gh CLI is authenticated.
=====================================
```

The block always includes:

| Field | Purpose |
|---|---|
| `Release` | The `--version` value being assured. |
| `Output directory` | The `--output` directory for the assurance pack. |
| `Failed check` | The name of the first check that failed. |
| `Command/function` | The command or internal operation that produced the failure evidence. |
| `Exit code` | The command exit code, when available. |
| `Stdout excerpt` | Up to the last 500 characters of stdout, redacted. |
| `Stderr excerpt` | Up to the last 500 characters of stderr, redacted. |
| `Remediation` | A human-readable hint for fixing the underlying issue. |

The script also writes a `release-assurance-summary.json` to the output directory as usual. The stderr diagnostic is independent of the optional JSON file and is always emitted on failure.

## What is redacted and why

Credential-like values are removed from diagnostic output before printing or serialization. The redaction patterns cover:

- Environment variable assignments matching `*_TOKEN` (for example `GH_TOKEN=<value>` or `GITHUB_TOKEN=<value>`).
- GitHub personal access tokens (`ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_` prefixes).
- Generic API keys such as `sk-...` style secrets and Alpaca API key identifiers.
- `Bearer <token>` authorization headers.
- Account-like UUIDs.

These values are replaced with `<redacted>` so that diagnostic excerpts remain useful for debugging without leaking secrets into CI logs, local terminals, or saved JSON files.

This is a defense-in-depth measure. You should still treat any generated diagnostic file as local evidence and avoid publishing it. See [Generated Artifacts](../development/generated-artifacts.md) for handling guidance.

## How to use `--diagnostics-json`

Add `--diagnostics-json <path>` to a `release_assurance.py` invocation:

```bash
python scripts/release_assurance.py \
  --version v0.6.11 \
  --output artifacts/release_assurance/v0.6.11-local-check \
  --diagnostics-json release-assurance-diagnostics.json
```

The file is written only when the script exits with a failure. If all checks pass, the file is not created and the script exits normally. This avoids leaving stale diagnostic files alongside successful runs.

The JSON schema is versioned as `atlas-release-assurance-diagnostics/1.0` and contains:

| Key | Description |
|---|---|
| `schema_version` | `atlas-release-assurance-diagnostics/1.0` |
| `passed` | `false` |
| `release` | The release version being assured |
| `failed_phase` | `release_assurance` |
| `failed_check` | The first failing check name |
| `command` | The command or function that produced the failure evidence |
| `exit_code` | Command exit code, when available |
| `stdout_excerpt` | Redacted stdout excerpt |
| `stderr_excerpt` | Redacted stderr excerpt |
| `remediation` | Human-readable remediation hint |
| `redactions_applied` | List of redaction categories applied |

## Workflow diagnostics artifact

The manual [Release Assurance workflow](../../.github/workflows/release-assurance.yml)
has an opt-in input, `upload_diagnostics_json` (default `false`). When set to `true`,
if `release_assurance.py` fails, the workflow uploads the redacted diagnostics JSON
as a `release-assurance-diagnostics` artifact.

Dispatch with diagnostics upload:

```bash
gh workflow run release-assurance.yml \
  --repo usernotfinded/atlas-agent \
  --field release=v0.6.11 \
  --field upload_diagnostics_json=true
```

To validate the diagnostics JSON before upload, also set `validate_diagnostics_artifact=true`:

```bash
gh workflow run release-assurance.yml \
  --repo usernotfinded/atlas-agent \
  --field release=v0.0.0-does-not-exist \
  --field upload_diagnostics_json=true \
  --field validate_diagnostics_artifact=true
```

The validator runs only when release assurance failed, `upload_diagnostics_json=true`,
and `validate_diagnostics_artifact=true`. The artifact is uploaded only if validation
succeeds. The workflow still fails afterward because release assurance failed.

Download the artifact after the run:

```bash
gh run download <run-id> --name release-assurance-diagnostics --dir ./diagnostics
```

The artifact only appears when the workflow fails and diagnostics are enabled.
If the workflow succeeds, no diagnostics file is created and the upload step is skipped.
The workflow still fails after uploading the diagnostics artifact.

## How to debug workflow failures

The [Release Assurance workflow](../../.github/workflows/release-assurance.yml) runs `release_assurance.py` in GitHub Actions. If it fails:

1. Open the failed workflow run.
2. Expand the step that ran `release_assurance.py` and read the `=== Release Assurance Diagnostic ===` block in the job log stderr.
3. If the workflow was invoked with `diagnostics_json` set, download the uploaded `release-assurance-diagnostics.json` artifact and inspect the redacted `stdout_excerpt`, `stderr_excerpt`, and `remediation` fields.
4. Apply the remediation locally and re-run the workflow.

Because output is redacted, you may need to reproduce the failure locally with the same environment variables to inspect the unredacted cause. Do not paste unredacted secrets or tokens into issue comments, logs, or shared artifacts.

## Examples

### Missing GitHub token

If `gh release view` fails because `GH_TOKEN` is not set and no GitHub CLI authentication is present, the diagnostic block shows:

```text
Failed check: github_release_present
Command/function: gh release view v0.6.11 --json url
Exit code: 4
Stderr excerpt:
To get started with GitHub CLI, please run: gh auth login
Alternatively, populate the GH_TOKEN environment variable...
Remediation: Create a GitHub release for v0.6.11 or verify GH_TOKEN is set and gh CLI is authenticated.
```

The `GH_TOKEN` value itself is never printed. In CI, the workflow sets `GH_TOKEN: ${{ github.token }}` automatically, so this failure usually means the repository token was not available.

### Missing release or tag

If the local tag, remote tag, or GitHub release does not exist:

```text
Failed check: local_tag_present
Command/function: git tag -l v0.6.11
Exit code: 0
Stdout excerpt:

Remediation: Create local tag with: git tag v0.6.11
```

or:

```text
Failed check: github_release_present
Command/function: gh release view v0.6.11 --json url
Exit code: 1
Stderr excerpt:
HTTP 404: Not Found (https://api.github.com/repos/...)
Remediation: Create a GitHub release for v0.6.11 or verify GH_TOKEN is set and gh CLI is authenticated.
```

These diagnostics indicate that the release artifact does not yet exist. Create the tag or release before re-running assurance; do not bypass the check.

### Artifact validation failure

If a manifest, secret, or forbidden-claim check fails inside an assurance bundle demo, the failing check may be reported as a reviewer trust snapshot validation failure or as an assurance summary validation failure. The diagnostic excerpt points to the underlying validation error. For example:

```text
Failed check: reviewer_trust_snapshot_valid
Command/function: check_reviewer_trust_snapshot.run_checks
Stderr excerpt:
Missing required file: reviewer-trust-snapshot.json
Remediation: Run scripts/check_reviewer_trust_snapshot.py on the snapshot directory.
```

The exact stderr depends on the validation script. The diagnostics JSON captures the same excerpt for machine-readable triage.

## No secrets are printed

Release assurance diagnostics never print credential values. Even when the underlying command output contains a token, key, account ID, or Bearer authorization header, the value is replaced with `<redacted>` before it reaches `stderr` or the JSON file.

If you encounter a diagnostic that appears to contain an unredacted secret, treat it as a bug and rotate the exposed credential immediately.

## Validating a downloaded diagnostics artifact

`scripts/check_release_assurance_diagnostics_artifact.py` validates a downloaded `release-assurance-diagnostics.json` artifact, a directory containing it, or a downloaded `.zip`.

Validate the artifact after downloading:

```bash
python3.11 scripts/check_release_assurance_diagnostics_artifact.py \
  ./local-diagnostics \
  --expect-release v0.0.0-does-not-exist
```

If you know which check failed, add `--expect-failed-check`:

```bash
python3.11 scripts/check_release_assurance_diagnostics_artifact.py \
  ./local-diagnostics/release-assurance-diagnostics.json \
  --expect-release v0.0.0-does-not-exist \
  --expect-failed-check package_version_aligned
```

Emit machine-readable JSON output:

```bash
python3.11 scripts/check_release_assurance_diagnostics_artifact.py \
  ./local-diagnostics --json
```

### What the validator checks

- **Schema**: required fields are present and `schema_version` is `atlas-release-assurance-diagnostics/1.0`.
- **Failure semantics**: by default `passed` must be `false`. Use `--allow-passed` only when validating a successful-run diagnostics file.
- **Release identity**: `release` is a non-empty string and matches `--expect-release` when provided.
- **Failed check**: `failed_check` is non-empty when `passed` is `false` and matches `--expect-failed-check` when provided.
- **Remediation**: a non-empty remediation hint is present.
- **Redactions**: `redactions_applied` is a non-empty list.
- **Safety scan**: every string value is scanned for unredacted secrets, credentials, account IDs, and unsafe publishing commands:
  - `GH_TOKEN=...`, `GITHUB_TOKEN=...`, and any `*_TOKEN=...` assignment with an unredacted value.
  - GitHub token prefixes (`ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`).
  - `sk-...` API keys.
  - `APCA-...` keys.
  - `Bearer <token>` authorization headers.
  - UUID-like account IDs.
  - Unsafe commands such as `git push`, `git tag`, `gh release create`, `gh release upload`, `twine upload`, and `twine publish`.

### What the validator does not prove

- It does not prove that the workflow run was free of manual intervention or environment compromise.
- It does not prove that the redaction patterns are exhaustive for every possible secret format.
- It does not prove that the underlying failure cause has been fixed locally.
- It does not replace an external security audit or manual secret rotation after a suspected leak.

If the validator reports an unredacted secret, treat the artifact as unsafe, rotate the exposed credential, and file a bug against the redaction patterns in `scripts/release_assurance.py`.

## Revalidating a diagnostics artifact in GitHub Actions

After a `release-assurance-diagnostics` artifact has been uploaded by a failed [Release Assurance workflow](../../.github/workflows/release-assurance.yml) run, you can re-download and re-validate it with the separate manual workflow [Release Assurance Diagnostics Artifact Validate](../../.github/workflows/release-assurance-diagnostics-artifact-validate.yml).

This workflow is `workflow_dispatch` only, declares only `contents: read` and `actions: read` permissions, and uses only the repository-provided read-only token (`GH_TOKEN: ${{ github.token }}`). It does not create tags, releases, or packages, and it does not call providers, brokers, or enable live trading.

### Required input

- `source_run_id` — the GitHub Actions run ID that produced the `release-assurance-diagnostics` artifact.

### Optional inputs

- `artifact_name` — artifact name to download (default: `release-assurance-diagnostics`).
- `expect_release` — expected `release` value in the diagnostics JSON.
- `expect_failed_check` — expected `failed_check` value in the diagnostics JSON.
- `allow_passed` — allow diagnostics where `passed` is `true` (default: `false`).

### Example dispatch

Revalidate the diagnostics artifact from the controlled-failure run:

```bash
gh workflow run release-assurance-diagnostics-artifact-validate.yml \
  --repo usernotfinded/atlas-agent \
  --field source_run_id=27639645906 \
  --field artifact_name=release-assurance-diagnostics \
  --field expect_release=v0.0.0-does-not-exist \
  --field expect_failed_check=package_version_aligned \
  --field allow_passed=false
```

The workflow downloads the source artifact, validates it with `scripts/check_release_assurance_diagnostics_artifact.py`, writes a JSON validation report to `artifacts/release_assurance_diagnostics_revalidation/diagnostics-artifact-validation.json`, and uploads that report as a `release-assurance-diagnostics-validation` artifact. The workflow fails if validation fails.

### Downloading the validation report

After the revalidation run completes, download the report with:

```bash
gh run download <run-id> --name release-assurance-diagnostics-validation --dir ./validation-report
```

The report JSON contains the same fields emitted by the validator's `--json` flag, including `passed`, `artifact_path`, `diagnostics_path`, `summary`, `errors`, and `warnings`.

## Safety constraints

Release assurance diagnostics are produced by a read-only, non-publishing script:

- No Git tag is created.
- No GitHub release is created.
- No package is published to PyPI.
- No provider is called.
- No broker is contacted.
- No live trading or order submission is enabled.
- No repository file is modified.

The diagnostics output itself is also read-only: it describes a failure but does not change configuration, safety defaults, or runtime boundaries. The validator is also static, local-only, and read-only; it makes no network calls and loads no credentials.
