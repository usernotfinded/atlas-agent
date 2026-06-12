# Contributor Onboarding

Atlas Agent is a safety-first trading framework. Local development should stay
paper-first, deterministic where possible, and free of real credentials unless a
task explicitly requires owner-approved local configuration.

## Requirements

- Python 3.11.
- Git.
- A local virtual environment.
- Dev extras installed from this repository.
- No real credentials required for the standard onboarding checks.
- No provider calls required for the standard onboarding checks.
- No broker calls required for the standard onboarding checks.
- Live trading is disabled by default.
- Provider execution is disabled by default.

GitHub CLI is useful for maintainers, but it is not required for ordinary local
checks.

## Clone and Environment Setup

Clone the repository, enter the checkout, and create an isolated Python 3.11
environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Use the virtual environment for local commands so the console scripts and dev
dependencies resolve consistently.

## Install Dev Dependencies

The editable install with dev extras is the contributor default:

```bash
python -m pip install -e ".[dev]"
```

If dependencies drift, reinstall the same dev extras instead of committing
generated package metadata or local build outputs.

## First Sanity Checks

Start with the fast local checks:

```bash
python scripts/check_version_consistency.py
python scripts/check_forbidden_claims.py
python scripts/check_trust_center.py
python scripts/check_generated_artifacts.py
python scripts/check_github_actions_versions.py
python scripts/main_health.py
./scripts/dev_check.sh
./scripts/ci_check.sh
./scripts/release_check.sh --quick
```

These checks are local. They do not require real credentials, provider calls,
broker calls, live trading, live submit, provider execution, or broker
execution.

## Safe Local Commands

Safe local commands include:

- `python scripts/check_version_consistency.py`
- `python scripts/check_forbidden_claims.py`
- `python scripts/check_trust_center.py`
- `python scripts/check_onboarding_docs.py`
- `python scripts/check_generated_artifacts.py`
- `python scripts/check_github_actions_versions.py`
- `python scripts/main_health.py`
- `python scripts/doctor.py`
- `./scripts/dev_check.sh`
- `./scripts/ci_check.sh`
- `./scripts/release_check.sh --quick`
- `PYTHONPATH=src python -m atlas_agent.cli update check --dry-run`

Paper-mode and dry-run commands are preferred during onboarding. Funded or live
broker use requires explicit local operator configuration and is outside the
normal contributor setup.

GitHub Actions maintenance policy is documented in
[GitHub Actions Maintenance](github-actions.md). Workflow action updates should
preserve Python 3.11, read-only permissions, safety environment defaults, and
non-publishing behavior.

## Evidence and Assurance Commands

Generate local release assurance evidence:

```bash
python scripts/release_assurance.py --version v0.6.9 --output artifacts/release_assurance/v0.6.9-local-check
```

Generate and verify a local provider audit pack:

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

Check updater delivery without installing anything:

```bash
PYTHONPATH=src python -m atlas_agent.cli update check --dry-run
```

These evidence commands create local artifacts or read public release metadata.
They do not authorize provider execution, broker execution, live trading, live
submit, or order approval.

## Git Workflow

Atlas Agent maintenance work follows `AGENTS.md`: **work directly on `main`**.
Keep the diff focused on the task, stage only intended files, and do not merge
until checks pass. For contributor work that is not direct-main maintenance,
use a feature branch and open a draft PR for review.

- Check [Generated Artifacts](generated-artifacts.md) before staging local
  evidence outputs.
- After direct-main maintenance pushes, check [Main Health Report](main-health.md)
  to verify local `main`, `origin/main`, optional GitHub CI visibility, artifact
  hygiene, and release/tag safety.
- Do not commit generated local artifacts unless the task explicitly requires a
  versioned evidence pack.

Before staging, check protected runtime boundaries:

```bash
git diff --name-status -- \
  src/atlas_agent/config \
  src/atlas_agent/brokers \
  src/atlas_agent/execution \
  src/atlas_agent/safety \
  src/atlas_agent/risk
```

Expected output for docs/checker/onboarding work is no output.

## Pull Request Checklist

- Version consistency passes.
- Forbidden-claims scan passes.
- Trust center check passes.
- Onboarding docs check passes.
- `./scripts/dev_check.sh` passes.
- `./scripts/ci_check.sh` passes when feasible.
- `./scripts/release_check.sh --quick` passes before review.
- The protected-boundary diff is empty for docs/checker-only work.
- Generated artifacts are excluded unless explicitly requested.
- The PR description states whether runtime behavior changed.

For this onboarding flow, expected runtime behavior change is none.

## Common Failure Modes

- The virtual environment is not active, so commands use a different Python
  version.
- Dev extras are missing, so tests or CLI imports cannot resolve dependencies.
- The worktree contains generated `artifacts/` output that should stay local.
- Release checks fail because unrelated files are staged.
- Tags were not fetched, so release-assurance or updater checks cannot confirm
  local tag state.
- A public doc accidentally implies live trading readiness, autonomous trading,
  or financial advice.

Use `python scripts/doctor.py` for a local environment summary before a larger
debugging session.

## Safety Rules

- Do not commit real credentials or credential-like values.
- Do not read or print secret values during diagnostics.
- Do not enable live trading defaults.
- Do not enable live submit defaults.
- Do not enable provider execution defaults.
- Do not enable broker execution defaults.
- Do not bypass risk gates, approval gates, kill switch behavior, audit logs, or
  manifests.
- Do not create tags, create GitHub releases, or publish to PyPI during normal
  contributor development.
