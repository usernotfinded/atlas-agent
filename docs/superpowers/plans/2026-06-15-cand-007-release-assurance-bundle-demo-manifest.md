# CAND-007 — Release Assurance Bundle End-to-End Demo and Artifact Manifest

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local, offline, credential-free end-to-end demo script plus an
artifact manifest builder/checker that compares release assurance bundles with
and without the reviewer trust snapshot.

**Architecture:** A bash demo orchestrates two invocations of
`scripts/release_assurance.py`, then builds and validates a JSON manifest using
two small Python scripts. Tests exercise the manifest checker with fixtures and
the demo with the existing public tag. Gate integration adds only fast
manifest/checker tests.

**Tech Stack:** Python 3.11, bash, pytest, pathlib, hashlib, json.

---

### Task 1: Implement `scripts/build_release_assurance_bundle_manifest.py`

**Files:**
- Create: `scripts/build_release_assurance_bundle_manifest.py`

**Behavior:**
- Accept `--baseline-dir`, `--snapshot-dir`, `--release`, `--output-dir`, and
  optional `--deterministic`.
- Discover files in each bundle (excluding `sha256sums.txt` from the file list).
- Record whether `reviewer-trust-snapshot/` exists in each bundle.
- Compute SHA-256 of every generated file and of the manifest itself.
- Write `release-assurance-bundle-manifest.json` to `--output-dir`.

- [ ] **Step 1: Write the failing test** (Task 5 will add tests; here implement first). Actually, implement first per user-driven spec, then add tests.
- [ ] **Step 2: Write minimal implementation**
- [ ] **Step 3: Run a quick smoke build**

```bash
python3.11 scripts/build_release_assurance_bundle_manifest.py \
  --baseline-dir /tmp/fake-baseline \
  --snapshot-dir /tmp/fake-snapshot \
  --release v0.6.11 \
  --output-dir /tmp/fake-manifest
```

- [ ] **Step 4: Commit**

### Task 2: Implement `scripts/check_release_assurance_bundle_manifest.py`

**Files:**
- Create: `scripts/check_release_assurance_bundle_manifest.py`

**Behavior:**
- Accept a manifest path or output directory.
- `--json` emits JSON.
- Validate schema, paths, snapshot presence/absence, checksums, safety
  invariants, no secrets, no forbidden claims, no unsafe commands.
- Exit 0 on pass, 1 on failure.

- [ ] **Step 1: Write minimal implementation**
- [ ] **Step 2: Run a quick smoke check**

```bash
python3.11 scripts/check_release_assurance_bundle_manifest.py /tmp/fake-manifest
```

- [ ] **Step 3: Commit**

### Task 3: Implement `scripts/demo_release_assurance_snapshot_bundle.sh`

**Files:**
- Create: `scripts/demo_release_assurance_snapshot_bundle.sh`
- Make executable.

**Behavior:**
- Parse `--help`, `--version`, `--output-dir`, `--deterministic`.
- Default `--version` to `v0.6.11`.
- Run release assurance twice:
  - baseline (no snapshot flag)
  - with snapshot flag
- Verify snapshot presence/absence.
- Run `check_reviewer_trust_snapshot.py` on opt-in snapshot.
- Build manifest with `build_release_assurance_bundle_manifest.py`.
- Validate manifest with `check_release_assurance_bundle_manifest.py`.
- Print summary.

- [ ] **Step 1: Write the script**
- [ ] **Step 2: Run `--help`**
- [ ] **Step 3: Run full demo to temp dir**

```bash
bash scripts/demo_release_assurance_snapshot_bundle.sh \
  --version v0.6.11 --output-dir "$(mktemp -d)" --deterministic
```

- [ ] **Step 4: Commit**

### Task 4: Add `tests/test_release_assurance_bundle_manifest.py`

**Files:**
- Create: `tests/test_release_assurance_bundle_manifest.py`

**Coverage:**
- `test_demo_help_works`
- `test_demo_rejects_unknown_option`
- `test_manifest_checker_passes_on_valid_temp_output`
- `test_manifest_checker_fails_snapshot_in_baseline`
- `test_manifest_checker_fails_snapshot_missing_in_opt_in`
- `test_manifest_checker_fails_credential_like_string`
- `test_manifest_checker_fails_forbidden_claim`
- `test_manifest_checker_json_output`
- `test_demo_runs_end_to_end` (marked `slow`)

- [ ] **Step 1: Write failing tests**
- [ ] **Step 2: Run tests and fix**

```bash
python3.11 -m pytest tests/test_release_assurance_bundle_manifest.py -q
```

- [ ] **Step 3: Commit**

### Task 5: Update gates

**Files:**
- Modify: `scripts/dev_check.sh`
- Modify: `scripts/ci_check.sh`
- Modify: `.github/workflows/ci.yml`

**Behavior:**
- Add `check_release_assurance_bundle_manifest.py` self-test or fixture-based
  check.
- Add pytest for `test_release_assurance_bundle_manifest.py` fast tests.
- Do not add slow full demo to CI.

- [ ] **Step 1: Edit scripts**
- [ ] **Step 2: Run gates locally**

```bash
./scripts/dev_check.sh
./scripts/ci_check.sh
```

- [ ] **Step 3: Commit**

### Task 6: Add/update docs

**Files:**
- Create: `docs/security/release-assurance-bundle-demo.md`
- Modify: `docs/security/release-readiness.md`
- Modify: `docs/trust/reviewer-trust-snapshot.md`
- Modify: `docs/reviewer-checklist.md` (if needed)
- Modify: `docs/trust/README.md` (if needed)

- [ ] **Step 1: Write new doc**
- [ ] **Step 2: Update cross-references**
- [ ] **Step 3: Commit**

### Task 7: Final validation

- [ ] Run full local validation suite.
- [ ] Fix failures.
- [ ] Stage explicit files and commit.
- [ ] Push to `origin/main`.
- [ ] Verify CI run.

```bash
python3.11 scripts/check_release_assurance_snapshot_integration.py
python3.11 scripts/check_reviewer_trust_snapshot_workflow.py
python3.11 scripts/check_docs_archive_hygiene.py
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/check_public_docs_consistency.py
python3.11 scripts/check_version_consistency.py
git diff --check
./scripts/dev_check.sh
./scripts/ci_check.sh
./scripts/release_check.sh --quick
```
