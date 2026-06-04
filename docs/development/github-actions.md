# GitHub Actions Maintenance

## Purpose

Atlas workflows use GitHub-hosted Actions for deterministic local-first checks,
release assurance, and provider audit evidence generation. This guide records the
current action version policy and the workflow boundaries that keep CI maintenance
separate from runtime trading behavior.

## Current Action Version Policy

Use these major action references in `.github/workflows/*.yml` and
`.github/workflows/*.yaml`:

- `actions/checkout@v6`
- `actions/setup-python@v6`
- `actions/upload-artifact@v6`

Run the static guard before staging workflow changes:

```bash
python3.11 scripts/check_github_actions_versions.py
python3.11 scripts/check_github_actions_versions.py --json
```

The guard is read-only. It scans workflow text locally, does not call the
network, and fails if one of the policy actions regresses to an older major such
as `actions/checkout@v4`, `actions/setup-python@v5`, or
`actions/upload-artifact@v4`.

## Node 24 Compatibility

The policy action majors are selected for Node 24-compatible GitHub Actions
runtimes. GitHub-hosted `ubuntu-latest` runners should support the required
runner version for `actions/setup-python@v6` and `actions/upload-artifact@v6`.

If self-hosted runners are ever added, check the runner version first.
`actions/setup-python@v6` and `actions/upload-artifact@v6` require Actions
Runner `v2.327.1+`.

## Workflow Safety Rules

Workflow maintenance must not change runtime trading defaults or execution
boundaries. Keep these environment values and safety assumptions intact unless a
task explicitly requires otherwise:

- `python-version: "3.11"`
- `permissions: contents: read`
- `ENABLE_LIVE_TRADING=false`
- `PROVIDER_EXECUTION_ENABLED=false`
- `BROKER_EXECUTION_ENABLED=false`
- `TRADING_MODE=paper`

Do not add secrets, provider calls, broker calls, live trading execution, direct
AI-to-broker execution, or release publishing behavior to CI maintenance.

## Manual Verification

For workflow-only maintenance, run:

```bash
python3.11 scripts/check_github_actions_versions.py
python3.11 scripts/check_generated_artifacts.py
python3.11 scripts/main_health.py
./scripts/dev_check.sh
./scripts/ci_check.sh
./scripts/release_check.sh --quick
```

After a direct-main push, use the main health report and optional GitHub CLI
visibility:

```bash
python3.11 scripts/main_health.py
python3.11 scripts/main_health.py --include-github
gh run list --branch main --limit 10
```

Do not claim GitHub CI is green unless the run status has been verified.

## What Not To Change

Do not change workflow triggers, permissions, branch filters, Python versions,
test commands, artifact paths, artifact retention settings, security environment
defaults, timeout settings, tag/release behavior, or PyPI behavior as part of
routine action-major maintenance.

Do not create tags, GitHub releases, or PyPI publishes from this maintenance
task unless the task explicitly requires those release actions and the owner has
approved the release workflow.
