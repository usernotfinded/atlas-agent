# CAND-007 — Release Assurance Bundle End-to-End Demo and Artifact Manifest

## Purpose

Add a safe, local, reproducible end-to-end demo that shows the release assurance
bundle behavior with and without the reviewer trust snapshot. The demo and its
manifest checker verify that:

- the baseline bundle is produced without the snapshot;
- the opt-in bundle is produced with the snapshot;
- both bundles can be validated by a manifest;
- no network, credentials, GitHub API, broker/provider execution, or tag/release
  actions are required.

## Scope

This candidate only adds demo, manifest, and test artifacts. It does not modify
`scripts/release_assurance.py` defaults, protected runtime boundaries, or any
live/provider/broker execution path.

## Components

### 1. `scripts/demo_release_assurance_snapshot_bundle.sh`

A bash demo script with the following behavior:

- `--help` / `-h` prints usage.
- `--version <tag>` defaults to `v0.6.11` (current public release).
- `--output-dir <path>` writes the demo result to a directory.
- `--deterministic` passes `--deterministic` to the reviewer trust snapshot builder
  (via `release_assurance.py`).
- Creates two subdirectories inside the output dir:
  - `baseline/` — release assurance without the snapshot.
  - `with-reviewer-trust-snapshot/` — release assurance with the snapshot.
- Verifies:
  - baseline does not contain `reviewer-trust-snapshot/`;
  - opt-in output contains `reviewer-trust-snapshot/`;
  - `check_reviewer_trust_snapshot.py` passes on the opt-in snapshot.
- Invokes `scripts/build_release_assurance_bundle_manifest.py` to generate a
  `release-assurance-bundle-manifest.json` at the output root.
- Invokes `scripts/check_release_assurance_bundle_manifest.py` to validate the
  manifest.
- Prints a clear summary.
- Fails closed on invalid args or verification failures.
- Requires no network and no credentials.

### 2. `scripts/build_release_assurance_bundle_manifest.py`

Builds `release-assurance-bundle-manifest.json` from a pair of release assurance
output directories. Schema fields:

- `schema_version`: `"atlas-release-assurance-bundle-manifest/1.0"`
- `release`: requested release tag
- `generated_at`: ISO-8601 timestamp
- `baseline_bundle`: path, relative path, file list, reviewer snapshot present flag
- `snapshot_bundle`: path, relative path, file list, reviewer snapshot present flag
- `reviewer_trust_snapshot_included`: mapping of bundle name -> bool
- `generated_files`: list of generated file entries (relative path, sha256)
- `checksums`: top-level sha256 of manifest and key artifacts
- `safety_invariants`: required safety booleans
- `commands`: commands used to produce the bundles
- `validation_summary`: result of manifest validation

### 3. `scripts/check_release_assurance_bundle_manifest.py`

Validates a manifest or an output directory containing a manifest:

- release version/tag field present;
- baseline path exists and does not contain reviewer trust snapshot;
- opt-in path exists and contains reviewer trust snapshot;
- required files exist in each bundle;
- checksums verify (sha256 of files listed in manifest);
- safety invariants present and correct;
- no credential-like strings in bundle files;
- no forbidden claims in bundle files;
- no tag/release/PyPI publish command evidence;
- `--json` output support;
- fails closed on violations.

### 4. `tests/test_release_assurance_bundle_manifest.py`

Covers:

- demo `--help` works;
- demo rejects unknown option;
- manifest checker passes on valid fixture/temp output;
- checker fails when snapshot appears in baseline;
- checker fails when snapshot missing from opt-in output;
- checker fails on credential-like strings;
- checker fails on forbidden claims;
- checker JSON output works;
- local demo can run in temp dir using existing public tag (marked `slow` if
  runtime is high).

### 5. `docs/security/release-assurance-bundle-demo.md`

Documents the demo, manifest, and validation. Mentions what it proves and does
not prove, that it uses the current public tag/release, and that no
publishing/tagging occurs.

### 6. Gate integration

Add fast manifest checker/test invocation to `scripts/dev_check.sh` and
`scripts/ci_check.sh` and `.github/workflows/ci.yml` if runtime is acceptable.
The full shell demo is reserved for manual/local verification; tests use
fixtures or a deterministic subset.

## Safety invariants

- Default `release_assurance.py` behavior unchanged.
- Snapshot generation remains opt-in.
- No live trading, broker/provider execution, credentials, secrets, or network
  calls.
- No tag/release/PyPI creation.
- No protected runtime boundary modifications.

## Success criteria

- `bash scripts/demo_release_assurance_snapshot_bundle.sh --help` prints usage.
- `bash scripts/demo_release_assurance_snapshot_bundle.sh --version v0.6.11 \
  --output-dir <tmp> --deterministic` exits 0 and produces both bundles plus a
  manifest.
- `python3.11 scripts/check_release_assurance_bundle_manifest.py <output>` exits 0.
- `python3.11 -m pytest tests/test_release_assurance_bundle_manifest.py -q` passes.
- `scripts/dev_check.sh`, `scripts/ci_check.sh`, and `scripts/release_check.sh --quick`
  pass.
- CI is green after push to `origin/main`.
