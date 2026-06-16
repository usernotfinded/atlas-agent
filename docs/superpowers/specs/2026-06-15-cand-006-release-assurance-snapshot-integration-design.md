# CAND-006 Design: Optional Release Assurance Bundle Integration for Reviewer Trust Snapshot

## Goal

Add a low-risk, opt-in integration so `scripts/release_assurance.py` can include a
reviewer trust snapshot inside the release assurance output directory when
explicitly requested, without changing default release assurance behavior.

## Approved approach

**Direct opt-in flag** in `scripts/release_assurance.py`.

- New CLI flag: `--include-reviewer-trust-snapshot`.
- Default behavior is unchanged (flag absent → no snapshot generated).
- With the flag, after the assurance pack is written, build a deterministic
  reviewer trust snapshot into `<output>/reviewer-trust-snapshot/`.
- Validate the snapshot with `scripts/check_reviewer_trust_snapshot.py` logic.
- If validation fails, `release_assurance.py` exits non-zero.
- The snapshot uses deterministic mode so CI artifacts are stable and diffable.

## Components

### 1. `scripts/release_assurance.py`

- Add `--include-reviewer-trust-snapshot` argument.
- Import `build_reviewer_trust_snapshot` and `check_reviewer_trust_snapshot`.
- If flag is set:
  - Compute `snapshot_dir = out_dir / "reviewer-trust-snapshot"`.
  - Call `build_reviewer_trust_snapshot.build_snapshot(snapshot_dir, deterministic=True)`.
  - Call `check_reviewer_trust_snapshot.run_checks(snapshot_dir)`.
  - If checks fail, append findings and set `valid = False`.
  - Record in `summary["reviewer_trust_snapshot_included"]` whether it was included and valid.
- If flag is not set, do not import builder/checker eagerly and do not create the subdirectory.

### 2. `.github/workflows/release-assurance.yml`

- Add `include_reviewer_trust_snapshot` workflow input, type `boolean`, default `false`.
- Pass the flag conditionally to the `release_assurance.py` invocation.
- Keep permissions as `contents: read`.
- No secrets, no publish, no tag/release/PyPI steps.

### 3. `scripts/check_release_assurance_snapshot_integration.py`

Static checker validating:

- `--include-reviewer-trust-snapshot` exists in `release_assurance.py` help/AST.
- Default behavior is documented/untouched (no unconditional snapshot call).
- No secrets references in the integration path.
- No `git push`, `git tag`, `gh release create`, `gh release upload`, `twine upload`, or PyPI publish commands.
- Builder/checker are invoked only through the opt-in path.
- No broker/provider/live execution commands.

CLI: human-readable output and `--json`.

### 4. `tests/test_release_assurance_snapshot_integration.py`

- Default run does not include snapshot.
- Opt-in run includes snapshot and validates it.
- Snapshot files exist (`reviewer-trust-snapshot.json`, `reviewer-trust-snapshot.md`, `checksums.sha256`).
- Checker passes on real repo.
- Checker fails on unsafe patterns (mocked unsafe workflow).
- CLI help includes the new flag.

### 5. Docs updates

Minimal updates to:

- `docs/trust/reviewer-trust-snapshot.md`
- `docs/security/release-readiness.md`
- `docs/trust/README.md`
- `docs/reviewer-checklist.md`

Explain: optional, local-only, no provider/broker/live trading, no tag/release/PyPI,
does not prove profitability or production readiness.

### 6. Gate integration

Add to:

- `scripts/dev_check.sh`
- `scripts/ci_check.sh`
- `.github/workflows/ci.yml`

Run `check_release_assurance_snapshot_integration.py` and focused pytest file.

## Safety invariants

- Default release assurance behavior unchanged.
- Snapshot integration opt-in only.
- No runtime behavior changed.
- Live trading, provider execution, broker execution remain disabled.
- No credentials loaded.
- No unsafe autonomy/profit/no-risk claims added.
- No tag/release/PyPI created.

## Out of scope

- Changing default release assurance behavior.
- Making release assurance depend on the snapshot.
- Adding network/GitHub API calls to local checks.
- Modifying protected runtime boundaries (`src/atlas_agent/{config,brokers,execution,safety,risk}`).
