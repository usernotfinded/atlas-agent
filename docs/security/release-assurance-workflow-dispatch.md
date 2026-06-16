# Release Assurance Workflow Dispatch

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## What this workflow does

The [Release Assurance workflow](../../.github/workflows/release-assurance.yml) is a manual `workflow_dispatch` job that generates a release assurance pack for a chosen release tag. When the optional input `run_bundle_demo` is set to `true`, it also runs `scripts/demo_release_assurance_snapshot_bundle.sh` and uploads the resulting directory as the `release-assurance-bundle-demo` artifact.

The artifact contains:

- `baseline/` — release assurance output generated **without** a reviewer trust snapshot.
- `with-reviewer-trust-snapshot/` — release assurance output generated **with** `--include-reviewer-trust-snapshot`.
- `release-assurance-bundle-manifest.json` — manifest describing both bundles, file checksums, and safety invariants.

The workflow and the artifact checker are read-only, local-only, and credential-free. They do not create tags, create GitHub releases, publish to PyPI, call providers or brokers, enable live trading, or load secrets.

## How to dispatch the workflow

### Via the GitHub web UI

1. Go to **Actions → Release Assurance** in the repository.
2. Click **Run workflow**.
3. Use these safe input values:
   - `release`: `v0.6.11`
   - `include_reviewer_trust_snapshot`: `true`
   - `run_bundle_demo`: `true`
   - `bundle_demo_version`: `v0.6.11`
4. Click **Run workflow**.

### Via the GitHub CLI

```bash
gh workflow run release-assurance.yml \
  --repo usernotfinded/atlas-agent \
  --field release=v0.6.11 \
  --field include_reviewer_trust_snapshot=true \
  --field run_bundle_demo=true \
  --field bundle_demo_version=v0.6.11
```

You can then follow the run with:

```bash
gh run list --workflow=release-assurance.yml --repo usernotfinded/atlas-agent
```

## How to download the artifact

After the workflow run completes, download the artifact with the run ID:

```bash
gh run download <run-id> --name release-assurance-bundle-demo --dir ./local-artifact
```

The downloaded directory (or a `.zip` downloaded from the GitHub UI) can be validated locally.

## How to validate the artifact

Validate an extracted artifact directory:

```bash
python3.11 scripts/check_release_assurance_workflow_artifact.py ./local-artifact
```

Validate a downloaded `.zip` directly:

```bash
python3.11 scripts/check_release_assurance_workflow_artifact.py ./release-assurance-bundle-demo.zip
```

Emit machine-readable JSON output:

```bash
python3.11 scripts/check_release_assurance_workflow_artifact.py ./local-artifact --json
```

The checker verifies:

- The artifact root contains `baseline/`, `with-reviewer-trust-snapshot/`, and `release-assurance-bundle-manifest.json`.
- The manifest is valid JSON and passes `scripts/check_release_assurance_bundle_manifest.py`.
- The baseline bundle does **not** contain `reviewer-trust-snapshot/`.
- The opt-in bundle **does** contain `reviewer-trust-snapshot/` with `reviewer-trust-snapshot.json` and `reviewer-trust-snapshot.md`.
- If `reviewer-trust-snapshot/checksums.sha256` is present, it is valid.
- No credential-like strings, forbidden claims, or unsafe command evidence (`git push`, `git tag`, `gh release create/upload`, `twine upload/publish`) appear in any artifact text file.

Exit codes:

- `0` — artifact passed validation.
- `1` — blocking findings (schema, safety, secrets, unsafe commands, etc.).
- `2` — operational error (missing path, bad zip, manifest not found).

## What the artifact proves

- A deterministic, local-only demo can be reproduced in GitHub Actions for the chosen release tag.
- The reviewer trust snapshot is opt-in and absent from the baseline bundle.
- Safety invariants such as "live trading disabled by default" and "no profit claims" hold in the generated bundles.
- File integrity can be verified independently from the manifest checksums.
- The artifact contains no secret-like strings, forbidden marketing claims, or unsafe publishing commands.

## What the artifact does not prove

- It does not prove profitability, strategy correctness, or future performance.
- It does not prove production readiness or suitability for live trading.
- It does not prove real-market behavior, broker connectivity, or provider reliability.
- It does not replace an external security audit or funded-use due diligence.
- It does not verify that the generated checksums match a separately published official release artifact.
- It does not imply that the workflow run itself was free of manual intervention or environment compromise.

## Safety constraints

- The workflow is `workflow_dispatch` only and defaults `run_bundle_demo` to `false`.
- It declares `permissions: contents: read` only.
- It references no secrets.
- It does not push tags, create releases, or publish to PyPI.
- It does not call providers, submit broker orders, or enable live trading.
- The local artifact checker performs only static, read-only validation. It makes no network calls and loads no credentials.

## Related docs

- [Release Assurance Bundle Demo](release-assurance-bundle-demo.md) — local-only demo that builds the same structure.
- [Release Readiness](release-readiness.md) — full release assurance documentation.
- [Reviewer Trust Snapshot](../trust/reviewer-trust-snapshot.md) — compact release-identity and safety-posture summary.
