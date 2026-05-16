# atlas-agent-pr-review

## When to use this skill

- Reviewing a patch or pull request before merge
- Assessing the safety of a proposed change
- Checking test coverage for a diff
- Recommending blockers vs. non-blocking issues
- Deciding whether a change requires human review beyond AI review

## Files and areas this applies to

- Any file in the diff
- `tests/` (coverage assessment)
- `docs/` (docs-honesty assessment)
- `scripts/` (release and safety script impact)

## Non-negotiable rules

1. **Safety-critical changes require human review.** If a PR touches broker adapters, order execution, risk evaluation, audit integrity, kill switch, or live-mode guards, recommend human review even if the code looks correct.
2. **Breaking changes need justification and migration path.** If a PR changes public APIs, CLI behavior, or config schema, it must include a rationale and a compatibility plan.
3. **Test coverage must increase or stay flat for safety-critical code.** A PR that reduces test coverage in `brokers/`, `execution/`, `risk/`, `safety/`, or `audit/` is a blocker.
4. **Docs must be updated for user-visible changes.** If a PR adds a command, changes behavior, or fixes a bug with user impact, docs must be updated in the same PR or explicitly deferred with a TODO.
5. **Secrets and redaction must be verified.** Any new error path, log line, or JSON payload must be checked for secret leakage.
6. **Performance claims need evidence.** If a PR claims to improve performance, verify that benchmarks exist and show improvement.
7. **No runtime files committed.** Verify `.gitignore` coverage for any new file creation paths.

## Required checks

- [ ] Diff does not touch `brokers/`, `execution/`, `safety/`, `risk/`, or `audit/` without tests
- [ ] Diff does not reduce test coverage in safety-critical modules
- [ ] New error paths redact secrets
- [ ] New commands have `--help` text and are documented
- [ ] `.gitignore` updated for new runtime files
- [ ] `scripts/check_forbidden_claims.py` passes if docs changed
- [ ] `scripts/check_version_consistency.py` passes if version changed

## Required tests or verification commands

```bash
# Run the full test suite
python3.11 -m pytest -q

# Check the diff for safety-critical paths
git diff --name-only | grep -E "brokers|execution|safety|risk|audit"

# Run release checks if version or docs changed
./scripts/release_check.sh

# Check for secret leakage in new code
git diff | grep -E "API_KEY|SECRET|TOKEN|PASSWORD|bearer"
```

## Output format expected

When reviewing a PR, produce:
1. **Safety assessment** — does the PR touch live trading, audit, broker, or risk paths?
2. **Test coverage assessment** — are new safety-critical paths tested? Did coverage decrease?
3. **Docs assessment** — are user-visible changes documented?
4. **Blockers** — list of issues that must be fixed before merge
5. **Non-blocking issues** — list of issues that can be addressed post-merge
6. **Merge recommendation** — approve / approve with comments / request changes / require human review

## Common failure modes to avoid

- **Rubber-stamping safety-critical PRs.** A PR that touches live submit paths must be scrutinized regardless of author reputation.
- **Ignoring test coverage gaps.** A refactor that removes lines but does not add tests for new paths creates hidden risk.
- **Missing the docs impact.** A CLI behavior change without doc updates causes user confusion.
- **Focusing only on code, ignoring commit hygiene.** Staging `memory.sqlite`, audit logs, or build artifacts in a PR is a blocker.
- **Not checking the diff scope.** A PR titled "docs fix" that also changes broker adapter code is a red flag.
