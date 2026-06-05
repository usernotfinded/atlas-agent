# Safe Local Workflows

This guide classifies local commands by risk. It is intended for contributors,
reviewers, and maintainers who need repeatable development checks without
changing trading behavior.

## Safe By Default

These commands are safe by default for normal local development:

- `python scripts/check_version_consistency.py`
- `python scripts/check_forbidden_claims.py`
- `python scripts/check_trust_center.py`
- `python scripts/check_onboarding_docs.py`
- `python scripts/check_generated_artifacts.py`
- `python scripts/check_github_actions_versions.py`
- `python scripts/main_health.py`
- `./scripts/dev_check.sh`
- `./scripts/ci_check.sh`
- `./scripts/release_check.sh --quick`
- provider preflight commands such as `providers preflight` and
  `providers smoke-preflight-chain`
- `providers audit-pack`
- `providers verify-audit-pack`
- `python scripts/release_assurance.py`
- `PYTHONPATH=src python -m atlas_agent.cli update check --dry-run`

They are local or dry-run oriented. They do not require real credentials,
provider calls, broker calls, live trading, live submit, provider execution, or
broker execution.

`python scripts/check_github_actions_versions.py` is also local-only. It checks
workflow action majors such as `actions/checkout@v6`,
`actions/setup-python@v6`, and `actions/upload-artifact@v6` without GitHub
credentials or network access.

## Paper-Only / Dry-Run Commands

Paper and dry-run commands are the default contributor path:

```bash
PYTHONPATH=src python -m atlas_agent.cli update check --dry-run
```

Provider preflight and smoke-chain commands generate local evidence only. Passing
preflight validation does not authorize provider execution, broker execution,
live trading, live submit, or order approval.

## Provider Evidence Commands

Create and verify a local provider audit pack:

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

The provider audit-pack workflow is evidence-only. It is not an execution
enablement workflow.

## Release Assurance Commands

Generate local release assurance evidence:

```bash
python scripts/release_assurance.py --version v0.5.9.5 --output artifacts/release_assurance/v0.5.9.5-local-check
```

Release assurance checks identity, updater delivery, local safety checks,
provider audit evidence, and checksums. It must not be treated as permission to
create tags, create releases, publish packages, or enable live execution.

## Commands Requiring Explicit Owner Approval

These operations require explicit owner approval and should not appear in normal
contributor workflows:

- version bump
- `git tag`
- `gh release create`
- PyPI publish
- merge PR
- force push
- destructive cleanup
- live trading config
- live submit config
- provider execution enablement
- broker execution enablement

## Commands Not Allowed During Normal Development

The following are not allowed during normal development:

- `git reset --hard`
- `git clean`
- `stash pop`, `stash drop`, or `stash clear`
- publishing to PyPI
- creating tags/releases
- enabling live trading defaults
- enabling provider execution defaults
- committing secrets

If a repository cleanup or release-sensitive operation is truly required, stop
and ask the owner for explicit approval.

## Handling Dirty Worktrees

Dirty worktrees are common after evidence generation and local tests. Before
staging:

- inspect `git status --short`;
- keep generated artifacts local unless the task explicitly asks for a versioned
  evidence pack;
- stage only intended files;
- confirm protected runtime boundaries are unchanged for docs/checker work.

Do not use destructive cleanup commands as a normal workflow.

After direct-main maintenance pushes, run `python scripts/main_health.py` from a
clean `main` checkout to verify local `HEAD`, `origin/main`, artifact hygiene,
release/tag safety, and protected runtime boundary status. Use
`python scripts/main_health.py --include-github` only when optional GitHub CLI
visibility is available.

## Handling Generated Artifacts

`artifacts/` outputs are usually local evidence, not source. Only commit
artifacts when the task explicitly requires a versioned evidence pack. Prefer CI
artifact upload for generated assurance/audit packs. See
[Generated Artifacts](generated-artifacts.md) for the full cleanup policy.

Common local artifact paths include:

- `artifacts/release_evidence/`
- `artifacts/release_assurance/`
- `artifacts/provider_audit_pack/`
- `artifacts/provider_preflight_smoke/`

Before staging, run:

```bash
python scripts/check_generated_artifacts.py
git status --short
```

If generated evidence is untracked and no longer needed, remove exact confirmed
files only. Do not use destructive cleanup commands as a normal workflow.

## Handling Secrets

- Do not commit `.env.atlas` or other local credential files.
- Do not paste credential values into docs, tests, issue templates, or PR
  descriptions.
- Do not print environment values in diagnostics.
- Use placeholder names only, not credential-shaped example values.
- Keep the dashboard read-only and zero-secret.

## Troubleshooting Permission/Approval Timeouts

Some commands need network or GitHub access, such as fetching tags or checking a
GitHub release. If an approval or network operation times out:

- keep the local worktree unchanged;
- record which read-only verification could not complete;
- rerun the local checks that do not need network;
- do not replace the verification with release creation, tag creation, package
  publishing, force push, or destructive cleanup.
