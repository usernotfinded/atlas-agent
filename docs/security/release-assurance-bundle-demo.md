# Release Assurance Bundle Demo

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## What the demo does

`scripts/demo_release_assurance_snapshot_bundle.sh` runs an end-to-end, local-only release assurance demo. It produces two release-assurance bundles side by side and a machine-readable manifest that describes them:

- A **baseline** bundle generated without the reviewer trust snapshot.
- An **opt-in** bundle generated with `--include-reviewer-trust-snapshot`.
- A **manifest** (`release-assurance-bundle-manifest.json`) that records both bundles, their file checksums, and the safety invariants verified during the run.

The demo is deterministic when run with `--deterministic`, runs entirely offline, and requires no credentials, API keys, broker accounts, or live trading enablement.

## How to run it

```bash
bash scripts/demo_release_assurance_snapshot_bundle.sh \
  --version v0.6.11 \
  --output-dir <path> \
  --deterministic
```

- `--version` — release tag to assure (default: `v0.6.11`).
- `--output-dir` — empty directory where `baseline/`, `with-reviewer-trust-snapshot/`, and the manifest will be written.
- `--deterministic` — use stable timestamps and sorted output for reproducible test/diff behavior.

The script refuses to overwrite a non-empty output directory. It exits non-zero if either bundle fails validation or if the manifest check fails.

## Why it uses the current public tag/release v0.6.11

The demo uses `v0.6.11` because that is the current public GitHub release and source/package version. Pinning the demo to the current public release makes the output a stable, reviewable reference that matches the released tag, the trust center status, and the reviewer trust snapshot schema. It does not imply that `v0.6.11` is approved for live trading or it is safe to deploy with real funds.

## Artifacts created

Inside the output directory the demo creates:

| Path | Purpose |
|---|---|
| `baseline/` | Release assurance output generated **without** a reviewer trust snapshot. |
| `with-reviewer-trust-snapshot/` | Release assurance output generated **with** `--include-reviewer-trust-snapshot`. |
| `release-assurance-bundle-manifest.json` | Manifest describing both bundles, file checksums, safety invariants, and the commands used. |

Each release assurance bundle contains at least:

- `release-assurance-summary.json`
- `release-assurance-report.md`
- `sha256sums.txt`

The opt-in bundle additionally contains `reviewer-trust-snapshot/` with the snapshot JSON, Markdown, and checksum files.

## How to validate the manifest

After the demo finishes, validate the manifest independently:

```bash
python3.11 scripts/check_release_assurance_bundle_manifest.py <output-dir>
```

JSON output is available with `--json`:

```bash
python3.11 scripts/check_release_assurance_bundle_manifest.py <output-dir> --json
```

The checker verifies:

- Manifest schema version and required keys.
- Both bundles exist and contain the required files.
- Recorded SHA-256 checksums match the files on disk.
- The baseline bundle does **not** include a reviewer trust snapshot.
- The opt-in bundle **does** include a reviewer trust snapshot.
- Required safety invariants are set to their expected values.
- No secret-like patterns or forbidden marketing claims appear in bundle files.
- No manifest command starts with an unsafe publishing prefix such as `git push`, `git tag `, `gh release create`, or `twine upload`.

## What it proves

- Release assurance can be generated locally for the current public release.
- The reviewer trust snapshot is **opt-in** (`--include-reviewer-trust-snapshot`) and absent by default.
- The demo and validation are local/offline and credential-free.
- Safety invariants such as "live trading disabled by default" and "no profit claims" hold in the generated bundles.
- File integrity can be verified independently from the manifest checksums.

## What it does not prove

- It does not prove profitability, strategy correctness, or future performance.
- It does not prove production readiness or suitability for live trading.
- It does not prove real-market behavior, broker connectivity, or provider reliability.
- It does not replace an external security audit or funded-use due diligence.
- It does not verify that the generated checksums match a separately published official release artifact.

## Running the demo from GitHub Actions

The manual **Release Assurance** workflow (`.github/workflows/release-assurance.yml`) can optionally run this demo and upload the resulting bundle as a CI artifact.

1. Go to **Actions → Release Assurance** in the repository.
2. Click **Run workflow**.
3. Keep `run_bundle_demo` unchecked to preserve the existing behavior (only the standard release assurance pack is generated and uploaded).
4. Set `run_bundle_demo` to `true` to also run `scripts/demo_release_assurance_snapshot_bundle.sh`.
   - `bundle_demo_version` defaults to the current public release (`v0.6.11`).
5. The workflow validates the generated manifest with `scripts/check_release_assurance_bundle_manifest.py` and uploads the entire output directory as the `release-assurance-bundle-demo` artifact.

The optional path is disabled by default. It does not create tags, create GitHub releases, publish to PyPI, use secrets, call providers or brokers, enable live trading, or modify repository files.

## No tag/release/PyPI is created

The demo is read-only and non-publishing. It does not:

- Create a Git tag.
- Create a GitHub release.
- Publish to PyPI.
- Modify repository files.
- Call providers or brokers.
- Enable live trading or order submission.
- Load credentials or secrets.

The optional GitHub Actions path has the same constraints.

## Related docs

- [Release Readiness](release-readiness.md) — full release assurance documentation.
- [Reviewer Trust Snapshot](../trust/reviewer-trust-snapshot.md) — compact release-identity and safety-posture summary.
