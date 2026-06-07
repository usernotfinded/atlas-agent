# Checks Reference

This reference explains the project checks contributors are expected to use for
docs, safety messaging, release readiness, and local evidence generation.

## Core Checks

- `scripts/check_version_consistency.py` verifies package version metadata in
  `pyproject.toml` and `src/atlas_agent/__init__.py`.
- `scripts/check_forbidden_claims.py` scans public docs for prohibited safety or
  profit wording.
- `scripts/check_trust_center.py` keeps the trust center aligned with release,
  security, provider evidence, updater, and non-claim messaging.
- `scripts/check_onboarding_docs.py` keeps contributor onboarding docs aligned
  with safe local development rules.
- `scripts/check_generated_artifacts.py` prevents accidental staging or tracking
  of local-only evidence outputs and secret-like filenames.
- `scripts/check_github_actions_versions.py` prevents GitHub workflow action
  version regressions to deprecated Node 20-era action majors.
- `scripts/main_health.py` reports direct-main post-push health from local git
  metadata, with optional GitHub CLI visibility when requested.

## Development Checks

`scripts/dev_check.sh` is the fast local development gate. It runs core static
checks, targeted tests, `git diff --check`, cached diff whitespace validation,
and protected staged-file checks.

Use it before opening or updating a PR:

```bash
./scripts/dev_check.sh
```

## CI Checks

`scripts/ci_check.sh` mirrors the main local CI parity gate. It runs public docs
checks, trust center checks, onboarding docs checks, package checks, focused
tests, `pip check`, whitespace validation, and protected staged-file checks.

Use it when a change affects docs, checks, release readiness, packaging, or CI:

```bash
./scripts/ci_check.sh
```

## Release Checks

`scripts/release_check.sh --quick` delegates to the local development gate. It
is the release-adjacent quick safety check for ordinary PRs:

```bash
./scripts/release_check.sh --quick
```

This command does not create tags, create GitHub releases, or publish packages.

## Research Checks

`scripts/research_check.sh` runs the research-focused local gate:

```bash
./scripts/research_check.sh
```

Run it when research docs, research CLI behavior, fixtures, or offline research
workflows change.

## Trust Center Checks

`scripts/check_trust_center.py` validates the public trust center:

```bash
python scripts/check_trust_center.py
python scripts/check_trust_center.py --json
```

It checks current release messaging, PyPI not-published status, updater delivery
verification, release assurance, provider audit-pack evidence, safety defaults,
non-claims, and secret-like values.

## Provider Audit Checks

Provider evidence commands are local and non-authorizing:

```bash
PYTHONPATH=src python -m atlas_agent.cli providers audit-pack \
  --provider openrouter \
  --model "openrouter/auto" \
  --purpose "reviewer-smoke" \
  --max-context-chars 4000 \
  --output-dir artifacts/provider_audit_pack/reviewer-smoke

PYTHONPATH=src python -m atlas_agent.cli providers verify-audit-pack \
  artifacts/provider_audit_pack/reviewer-smoke
```

The provider audit-pack and verify-audit-pack commands create or validate local
evidence. They do not call providers, touch brokers, enable live trading, or
approve orders.

## Release Assurance Checks

`scripts/release_assurance.py` generates a local release assurance pack:

```bash
python scripts/release_assurance.py --version v0.6.3 --output artifacts/release_assurance/v0.6.3-local-check
```

The release assurance pack includes identity, updater delivery, local evidence,
checksum, and non-claim checks. It is not a publishing workflow.

Generated release assurance packs are local-only evidence. The report includes a
"Local Evidence" section with deterministic cleanup instructions. Do not commit
release assurance outputs unless a task explicitly requests a versioned evidence
pack. Run `python3.11 scripts/check_generated_artifacts.py` before staging to
confirm no generated artifacts are accidentally committed.

## Generated Artifact Hygiene Checks

`scripts/check_generated_artifacts.py` inspects git path metadata only:

```bash
python scripts/check_generated_artifacts.py
python scripts/check_generated_artifacts.py --json
```

It blocks tracked or staged local-only generated evidence, secret-like
filenames, and dangerous generated file types staged from `artifacts/`. It does
not remove files, stage files, unstage files, call the network, or read
credential values.

## Main Health Report

`scripts/main_health.py` is a read-only direct-main maintenance report:

```bash
python scripts/main_health.py
python scripts/main_health.py --json
python scripts/main_health.py --include-github
```

Default mode is local-only. It checks source version identity, public release
identity, branch state, `HEAD` versus `origin/main`, generated artifact hygiene,
protected runtime boundary status, and absence of an unrequested maintenance
tag. GitHub CLI visibility is optional and should not be made mandatory in CI.
See [Main Health Report](main-health.md).

## GitHub Actions Version Checks

`scripts/check_github_actions_versions.py` is a read-only workflow action
version guard:

```bash
python scripts/check_github_actions_versions.py
python scripts/check_github_actions_versions.py --json
```

It scans `.github/workflows/*.yml` and `.github/workflows/*.yaml` locally and
requires `actions/checkout@v6`, `actions/setup-python@v6`, and
`actions/upload-artifact@v6`. It does not call the network, install
dependencies, modify files, or require GitHub credentials. See
[GitHub Actions Maintenance](github-actions.md).

## v0.6.3 Release Prep Checks

`scripts/check_v063_release_prep.py` is a read-only checker for the v0.6.3 release
prep state:

```bash
python3.11 scripts/check_v063_release_prep.py
python3.11 scripts/check_v063_release_prep.py --json
```

It verifies that the package version is `0.6.3`, `docs/releases/v0.6.3.md` exists,
`docs/trust/v0.6.3-status.md` exists, the CHANGELOG has a `[0.6.3]` entry, and
no premature `v0.6.4` release notes exist.

## v0.6.1 Patch Candidate Checks

`scripts/check_v061_candidates.py` is a read-only checker for the v0.6.1 patch
candidate selection document:

```bash
python3.11 scripts/check_v061_candidates.py
python3.11 scripts/check_v061_candidates.py --json
```

It verifies that `docs/releases/v0.6.1-candidates.md` exists, contains required
sections (selection criteria, candidate table, accepted candidates, rejected
candidates, safety boundaries, non-goals), and does not select unsafe runtime scope.

See also [v0.6.1 Release Prep Checks](#v061-release-prep-checks),
[v0.6.0 Readiness Checks](#v060-readiness-checks), and
[Long-Running Checks](#long-running-checks) for related release verification.

## v0.6.1 Release Prep Checks

`scripts/check_v061_release_prep.py` is a read-only checker for the v0.6.1 release
prep state (historical or post-bump compatible):

```bash
python3.11 scripts/check_v061_release_prep.py
python3.11 scripts/check_v061_release_prep.py --json
```

It verifies that `docs/releases/v0.6.1.md` exists,
`docs/trust/v0.6.1-status.md` exists, the CHANGELOG has a `[0.6.1]` entry, and
no premature `v0.6.4` release notes exist. It accepts the current source version
being `0.6.2` or `0.6.3` as a valid post-bump state.

## v0.6.0 Readiness Checks

`scripts/check_v060_readiness.py` is a read-only checker for the v0.6.0
capability expansion audit:

```bash
python3.11 scripts/check_v060_readiness.py
python3.11 scripts/check_v060_readiness.py --json
```

Default mode is **pre-release**: it verifies required docs, source modules,
test files, CLI contract entries, CHANGELOG unreleased section, version
identity, absence of a premature v0.6.0 tag, forbidden claims, and generated
artifact hygiene.

After `v0.6.0` is published, use **post-release** mode to validate the
published state:

```bash
python3.11 scripts/check_v060_readiness.py --post-release
python3.11 scripts/check_v060_readiness.py --post-release --json
```

Post-release mode expects the `v0.6.0` tag to exist and checks that the
GitHub release is present (if GitHub CLI is available). It preserves all
other readiness checks. It does not call the network, require credentials,
create tags, create releases, or modify files.

## Protected Boundary Checks

Docs/checker/onboarding work should not touch protected runtime boundaries. Use:

```bash
git diff --name-status -- \
  src/atlas_agent/config \
  src/atlas_agent/brokers \
  src/atlas_agent/execution \
  src/atlas_agent/safety \
  src/atlas_agent/risk
```

Expected output for docs/checker-only work is no output.

## Dangerous Pattern Scans

Use this scan to classify release-sensitive, credential-sensitive, network, and
destructive-command matches in a diff:

```bash
git diff | grep -n -E 'twine|pypi|gh release|git push --tags|git tag|create-release|publish|PYPI|secrets\.|API_KEY|TOKEN|PASSWORD|curl|wget|ssh|scp|rsync|--force|--force-with-lease|reset --hard|git clean|stash pop|stash drop|skip|xfail|\|\| true|openai|anthropic|gemini|google\.genai|moonshot|kimi|xai|requests\.|httpx|urllib|socket' || true
```

Expected benign matches include:

- PyPI mentioned as not published.
- GitHub release mentioned in docs.
- fake secret names in tests.
- OpenRouter as a dry-run provider id.
- warnings against `git tag`, `gh release create`, force push, or destructive
  cleanup.

Blocking matches include actual publishing commands, actual tag/release creation
outside warning context, destructive git operations outside warning context,
provider/broker execution, live trading enablement, and real secret values.

## Long-Running Checks

Some local checks can take several minutes, especially on slower machines or
when the full test suite is large:

| Check | Typical local runtime | Category |
|---|---|---|
| `scripts/dev_check.sh` | ~30–90s | core |
| `scripts/ci_check.sh` | ~60–180s | core |
| `scripts/release_check.sh --quick` | ~30–90s | core |
| `scripts/research_check.sh` | ~60–300s | long |
| `scripts/release_check.sh --full` | ~120–600s | long |

**Timeout triage rules:**

- If a long-running check times out but all core gates pass, report it as
  **WARN / INCONCLUSIVE**, not PASS.
- Core gates remain: `dev_check.sh`, `ci_check.sh`, `release_check.sh --quick`.
- Do **not** weaken checks, add broad `|| true`, skip tests, or remove checks
  to avoid timeout.
- Use focused subsets for faster iteration (see `scripts/check_runtime_diagnostics.py`).
- Capture full output to a log for post-hoc analysis:
  ```bash
  ./scripts/release_check.sh --full 2>&1 | tee /tmp/release.log
  ```

All gate scripts print per-step elapsed time and a total elapsed summary.

## Runtime Diagnostics

`scripts/check_runtime_diagnostics.py` is a read-only helper that documents
expected commands, typical runtimes, focused subsets, and timeout triage
guidance without running any checks:

```bash
python scripts/check_runtime_diagnostics.py
python scripts/check_runtime_diagnostics.py --json
```

## Interpreting Failures

- Treat stale version, trust center, onboarding docs, and forbidden-claim
  failures as blocking until corrected.
- Treat dirty worktree output as a staging problem first: inspect, narrow the
  diff, and exclude generated artifacts unless requested.
- Treat provider audit and release assurance artifacts as local evidence unless
  the task explicitly asks for a versioned evidence pack.
- Do not bypass a failing check by weakening checks, removing version checks,
  adding broad skips, or changing runtime safety defaults.
