# Main Health Report

## Purpose

The main health report is a read-only post-push check for direct-main
maintenance work. It verifies local `main`, pushed commit visibility from local
git metadata, source package version identity, generated artifact hygiene,
release/tag safety, and protected runtime boundary status.

It does not install dependencies, modify files, stage files, unstage files,
commit, push, create tags, create GitHub releases, publish packages, call
providers, call brokers, read credentials, or change runtime trading behavior.

## When To Run

Run it after a direct push to `main`:

```bash
python3.11 scripts/main_health.py
python3.11 scripts/main_health.py --json
```

For optional GitHub Actions visibility:

```bash
python3.11 scripts/main_health.py --include-github
python3.11 scripts/main_health.py --include-github --json
```

The GitHub CLI visibility mode is optional. Missing GitHub CLI, missing auth, no
network, or no workflow runs should be treated as a visibility limitation, not a
local code failure.

## Local-Only Checks

Default mode is local-only and does not require network, GitHub credentials,
provider credentials, or broker credentials. It checks:

- repository root detection;
- `pyproject.toml` and `src/atlas_agent/__init__.py` version metadata;
- expected source version;
- current branch;
- local `HEAD` and `origin/main` commit alignment;
- working tree and staged-change status;
- generated artifact hygiene checker availability and result;
- trust center and onboarding checker availability;
- absence of an unrequested maintenance tag;
- absence of known release or publish artifacts staged locally;
- protected runtime boundary diff status.

## Optional GitHub CI Visibility

When `--include-github` is used, the report tries to inspect recent GitHub
Actions runs with:

```bash
gh run list --branch main --limit 5
```

Maintainers can also inspect more recent runs manually:

```bash
gh run list --branch main --limit 10
```

Do not claim GitHub CI is green unless the relevant run status and conclusion
were actually inspected. The health report is not a release creation workflow
and must not be used to create tags, create GitHub releases, or publish to PyPI.

## Expected Direct-Main State

After a direct-main maintenance push, expected state is:

- current branch is `main`;
- local `HEAD` matches `origin/main`;
- working tree is clean;
- no staged changes remain;
- no local generated evidence is staged;
- no unrequested maintenance tag exists;
- no protected runtime boundary diff is present for docs/checker-only work.

Dirty worktree output should be resolved before continuing. Inspect exact paths
with `git status --short`, then stage or remove only intentional files.

## Version and Release Identity

The main source version can differ from public release during maintenance
updates. After the v0.6.17 release, the source package version on `main` is `0.6.17`, the
current public release is `v0.6.17`, and the public GitHub release is `v0.6.17`. The
previous public release is `v0.6.16`. The next planning line is `v0.6.18`.

Do not create future tags, GitHub releases, or PyPI publishes unless the task
explicitly requests that release action. A maintenance source version is not a
public release by itself.

## Artifact Hygiene

Generated artifact hygiene is part of direct-main maintenance verification.
Generated artifacts should remain unstaged unless explicitly requested. Local
evidence outputs such as `artifacts/release_evidence/`,
`artifacts/release_assurance/`, `artifacts/provider_audit_pack/`, and
`artifacts/provider_preflight/` should normally stay local or be uploaded as CI
artifacts.

Run:

```bash
python3.11 scripts/check_generated_artifacts.py
```

See [Generated Artifacts](generated-artifacts.md) for the full policy.

For workflow maintenance, also run:

```bash
python3.11 scripts/check_github_actions_versions.py
```

See [GitHub Actions Maintenance](github-actions.md) for the Node 24-compatible
action version policy.

## Protected Runtime Boundaries

Protected runtime boundaries should be empty for docs/checker-only work:

```bash
git diff --name-status -- \
  src/atlas_agent/config \
  src/atlas_agent/brokers \
  src/atlas_agent/execution \
  src/atlas_agent/safety \
  src/atlas_agent/risk
```

If output appears for docs/checker-only work, stop and classify it before
staging. Do not change live trading defaults, provider execution defaults,
broker execution defaults, approval gates, risk controls, kill-switch behavior,
audit logs, or manifests as part of a health-report task.

## Interpreting Findings

- Version mismatches are blocking.
- A non-`main` branch is blocking for direct-main maintenance verification.
- `HEAD` not matching `origin/main` means the latest local commit is not aligned
  with the tracked remote state.
- An unrequested future release tag is blocking.
- Generated artifact hygiene findings are blocking.
- Missing GitHub CLI in `--include-github` mode is a warning.
- Untracked generated artifacts are warnings unless they become staged or
  tracked.

## Safe Follow-Up Actions

Use exact, read-only inspection first:

```bash
git status --short
python3.11 scripts/main_health.py
python3.11 scripts/check_generated_artifacts.py
```

If regenerated evidence files are local-only and not needed, remove exact
confirmed paths only:

```bash
rm artifacts/release_evidence/evidence.json
rm artifacts/release_evidence/evidence.md
```

- Do not use git reset --hard.
- Do not use git clean.
- Do not use stash pop.
- Do not use stash drop.
- Do not use stash clear.

Stage exact intended files only. Do not perform tag creation, GitHub release
creation, or PyPI publish follow-up unless the task explicitly requests it.
