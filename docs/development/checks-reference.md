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
python scripts/release_assurance.py --version v0.5.9 --output artifacts/release_assurance/v0.5.9-local-check
```

The release assurance pack includes identity, updater delivery, local evidence,
checksum, and non-claim checks. It is not a publishing workflow.

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

## Interpreting Failures

- Treat stale version, trust center, onboarding docs, and forbidden-claim
  failures as blocking until corrected.
- Treat dirty worktree output as a staging problem first: inspect, narrow the
  diff, and exclude generated artifacts unless requested.
- Treat provider audit and release assurance artifacts as local evidence unless
  the task explicitly asks for a versioned evidence pack.
- Do not bypass a failing check by weakening checks, removing version checks,
  adding broad skips, or changing runtime safety defaults.
