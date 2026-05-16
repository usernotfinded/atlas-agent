# atlas-agent-release-check

## When to use this skill

- Bumping the version in `pyproject.toml` and `src/atlas_agent/__init__.py`
- Cutting a Git tag
- Updating `CHANGELOG.md` or release notes
- Running smoke scripts (`smoke_release_tag.sh`, `smoke_package_build.sh`)
- Preparing a release candidate audit document
- Checking for untracked release-critical files

## Files and areas this applies to

- `pyproject.toml`
- `src/atlas_agent/__init__.py`
- `CHANGELOG.md`
- `docs/releases/*.md`
- `README.md` (version references and release links)
- `scripts/release_check.sh`
- `scripts/smoke_release_tag.sh`
- `scripts/smoke_package_build.sh`
- `scripts/check_version_consistency.py`
- `scripts/check_no_protected_staged.py`

## Non-negotiable rules

1. **Version must be consistent.** `pyproject.toml` `project.version` must equal `src/atlas_agent/__init__.__version__`. `scripts/check_version_consistency.py` must pass.
2. **CHANGELOG must document the release.** Every release needs a dated section in `CHANGELOG.md` with Added/Changed/Fixed/Safety headings.
3. **Release notes must exist for dev tags.** Create `docs/releases/vX.Y.Z.devN.md` with summary, highlights, safety notes, validation, and known limitations.
4. **README must reference the latest release.** Update the "Current Status" badge/link to point to the latest release notes.
5. **Smoke scripts must be documented.** If a smoke script is not run (e.g., requires network), state that explicitly in the release notes.
6. **No protected files staged.** `scripts/check_no_protected_staged.py` must pass before tagging. Do not commit runtime files, build artifacts, or planning documents.
7. **Tag must be annotated.** Use `git tag -a` with a descriptive message.

## Required checks

- [ ] `python3.11 scripts/check_version_consistency.py` passes
- [ ] `python3.11 scripts/check_forbidden_claims.py` passes
- [ ] `python3.11 scripts/check_no_protected_staged.py` passes
- [ ] `python3.11 -m pytest -q` passes
- [ ] `./scripts/demo_paper_workflow.sh` passes
- [ ] `./scripts/release_check.sh` passes
- [ ] `git diff --check` passes (no whitespace errors)
- [ ] `CHANGELOG.md` has an entry for the new version
- [ ] `docs/releases/v<VERSION>.md` exists
- [ ] `README.md` references the new version

## Required tests or verification commands

```bash
python3.11 scripts/check_version_consistency.py
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/check_no_protected_staged.py
python3.11 -m pytest -q
python3.11 -m pip check
./scripts/demo_paper_workflow.sh
git diff --check
./scripts/release_check.sh
```

## Output format expected

When preparing a release, produce:
1. Version number and consistency confirmation
2. CHANGELOG entry summary
3. Release notes file path
4. Smoke script status (run / not run / requires push first)
5. Protected staged file status
6. A go/no-go recommendation for tagging

## Common failure modes to avoid

- **Version mismatch.** Updating `pyproject.toml` but forgetting `__init__.py` causes installation and runtime version inconsistencies.
- **Missing release notes.** A tag without release notes forces users to read the full CHANGELOG for context.
- **Staging runtime files.** Committing `memory/`, `audit/`, or build artifacts pollutes the repository.
- **Running smoke tag script before pushing.** `smoke_release_tag.sh` clones from the remote; it fails if the tag is not pushed.
- **False smoke script claims.** Do not claim a smoke script passed if it was not run. State "not run in this environment" instead.
