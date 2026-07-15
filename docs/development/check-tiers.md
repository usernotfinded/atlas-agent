# Check Tiers

Atlas Agent provides tiered local checks so contributors can choose the right
balance of speed and coverage for each situation.

## Tier Summary

| Tier | Script | Target time | When to run |
|---|---|---|---|
| Smoke | `scripts/smoke_check.sh` | < 10 s | After small docs/checker edits |
| Local Quick | `scripts/local_quick_check.sh` | ~30–45 s | Before committing |
| Dev | `scripts/dev_check.sh` | ~55–90 s | Before opening/updating a PR |
| CI | `scripts/ci_check.sh` | ~60–180 s | When docs/checks/CI/packaging change |
| Release Quick | `scripts/release_check.sh --quick` | ~55–90 s | Release-adjacent quick safety check |
| Release Full | `scripts/release_check.sh --full` | ~120–600 s | Before push/tag |

## Smoke Check

```bash
./scripts/smoke_check.sh
```

**Purpose:** Catch the most common breaking changes during rapid edit loops.

**Includes:**
- `check_version_consistency.py`
- `check_forbidden_claims.py`
- `check_cli_command_compatibility.py`
- `check_submit_execution_safety.py`
- `git diff --check`
- `check_no_protected_staged.py`
- `pip check`
- `check_demo_command_smoke.py` (CAND-004)
- Focused pytest: `test_cli_smoke.py` + `test_submit_execution_safety_check.py`

**Skips:** trust center, onboarding, generated artifacts, GitHub Actions versions,
feedback taxonomy, product inventory, historical checkers, packaging checks,
research sandbox tests, reviewer golden-path smoke, and the full test suite.

## Local Quick Check

```bash
./scripts/local_quick_check.sh
```

**Purpose:** A balanced pre-commit gate that preserves all safety boundaries
while skipping low-value or subprocess-heavy work.

**Includes:**
- Everything in Smoke Check
- `check_demo_command_smoke.py` (CAND-004)
- `check_trust_center.py`
- `check_onboarding_docs.py`
- `check_generated_artifacts.py`
- `check_github_actions_versions.py`
- `verify_readme_quickstart.py`
- Feedback intake/taxonomy, reviewer outreach, product capability inventory
- `git diff --cached --check`
- Tests classified as `quick`. Tests under domain directories such as
  `tests/agent/`, `tests/execution/`, and `tests/risk/` join automatically;
  exceptional root-level tests can declare `@pytest.mark.quick`. Contributors
  do not maintain a shell-script path allowlist.

**Skips:**
- Historical release checker tests (`test_v058_*.py`, `test_v06[0-5]_*.py`)
- Subprocess-heavy integration tests:
  - `test_demo_research_workflow_script.py`
  - `test_package_distribution_check.py`
  - `test_clean_install_check.py`
  - `test_cli_ux_regression.py`
  - `test_reviewer_golden_path_smoke.py`
- Slow research tests (`test_research_provider_safety_dossier.py`,
  `test_research_sandbox_cli.py`)
- Real packaging/build checks (`check_clean_install.py`,
  `check_package_distribution.py`)
- Release-gate-only checks (public launch readiness/messaging, RC audit,
  stable release decision, reviewer onboarding)
- Tests marked `slow`, which are subprocess-heavy integration tests retained
  in the complete pytest suite and CI core-functional job

### Adding Tests Without Runner Maintenance

- Put fast tests in the matching domain directory (for example,
  `tests/risk/` or `tests/execution/`). They join the quick tier automatically.
- Mark an exceptional fast root-level test with `@pytest.mark.quick`.
- Mark subprocess-heavy integration coverage with `@pytest.mark.slow`.
- Use shared fixtures from `tests/conftest.py`; `mutated_copy` exists for
  checker fault injection so tests never edit live repository files.
- Test observable behavior and stable safety contracts. Avoid copying entire
  implementations or maintaining shell-script test-path lists.

Plain `pytest` remains the full gate, so tier classification changes local
feedback speed without removing coverage.

## Dev Check

```bash
./scripts/dev_check.sh
```

**Purpose:** Full local development gate before opening or updating a PR.

**Includes:** all Smoke Check items plus trust center, onboarding, generated
artifacts, GitHub Actions versions, feedback taxonomy, product inventory,
v0.5.8 historical checks, research sandbox CLI tests, reviewer golden-path
smoke tests, and release check script tests.

## CI Check

```bash
./scripts/ci_check.sh
```

**Purpose:** Local CI parity gate when changes affect docs, checks, release
readiness, packaging, or CI configuration.

**Includes:** everything in Dev Check plus public docs consistency, README
quickstart verification, RC cutover checks, clean install (dry-run and real),
package distribution (dry-run and real), public launch readiness/messaging,
reviewer onboarding, final RC audit, stable release decision, and a larger
focused pytest subset.

## Release Checks

```bash
./scripts/release_check.sh --quick   # delegates to dev_check.sh
./scripts/release_check.sh --full    # full release gate
```

**Purpose:** `--quick` is a convenience alias for the dev gate. `--full` is the
strict release gate required before push/tag.

**Full mode includes:** everything in CI Check plus the complete pytest suite,
reviewer golden-path smoke, paper demo workflow, and research demo workflow.

## Safety Boundaries

No tier skips these checks:

- `check_forbidden_claims.py`
- `check_submit_execution_safety.py`
- `check_no_protected_staged.py`
- `git diff --check`

These are non-negotiable safety gates that run even in the fastest smoke tier.

## Concurrency and Heat

None of the local check scripts use `pytest-xdist` or `-n auto` by default.
If you install `pytest-xdist` and want faster wall-clock time at the cost of
higher CPU/heat, you can override pytest arguments:

```bash
ATLAS_CHECK_PYTEST_ARGS="-n auto" ./scripts/local_quick_check.sh
```

The default serial execution is chosen to keep Macs cool during normal
development. CI runs the full suite in GitHub Actions workers.

The `quick` marker identifies deterministic edit-loop coverage. Tests in domain
directories receive it automatically. The `slow` marker identifies
subprocess-heavy CLI, end-to-end, and gate integration tests.
`tests/conftest.py` centralizes legacy integration and historical path
classification; new exceptional tests may declare either marker at their
source. `local_quick_check.sh` selects `quick`, while plain `python -m pytest`
still runs every test in both tiers.

## Historical Tests

Tests for historical release checkers (v0.5.8, v0.6.0–v0.6.6) are valuable for
regression safety but low-value for daily local development. They are excluded
from Smoke and Local Quick tiers. CI and Release Full still run them.
