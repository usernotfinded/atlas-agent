# atlas-agent-docs-honesty

## When to use this skill

- Editing `README.md`
- Editing `docs/` files (architecture, demos, safety contracts, release notes)
- Editing `CHANGELOG.md`
- Writing release notes or release candidate audits
- Any user-facing copy that describes capabilities, performance, or safety

## Files and areas this applies to

- `README.md`
- `docs/*.md`
- `CHANGELOG.md`
- `docs/releases/*.md`
- `docs/release-candidate-audit-*.md`
- Any new documentation file

## Non-negotiable rules

1. **Distinguish mock contracts from live integrations.** If a broker adapter has only a mock/test implementation, docs must say "contract defined" or "test implementation available," not "integrated with Broker X."
2. **No unsupported performance claims.** Do not claim "faster," "scalable," or "low latency" without benchmark artifacts. Use language like "local-first" or "deterministic" instead.
3. **No live-trading readiness overstatements.** A development tag is not production live-trading readiness. Use "development tag," "paper-only," and "explicitly gated" language.
4. **No profit or safety guarantees.** Avoid "zero risk," "risk-free," "guaranteed profit," "safe live trading," "autonomous income," or similar phrases.
5. **Accuracy over marketing.** Prefer precise, boring language over aspirational copy. If a feature is partial, say so.
6. **Release notes must list known limitations.** Every release note must include a "Known Limitations" section.
7. **Docs must match code.** If a command no longer exists or behavior changed, update the docs in the same commit.
8. **Forbidden claims scan must pass.** `scripts/check_forbidden_claims.py` checks for prohibited language. Ensure it passes after doc edits.

## Required checks

- [ ] `python3.11 scripts/check_forbidden_claims.py` passes
- [ ] No claims of live/production readiness for mock-only features
- [ ] Performance claims reference benchmark artifacts or are removed
- [ ] Known limitations section exists in release notes
- [ ] Command examples in docs match actual CLI behavior

## Required tests or verification commands

```bash
python3.11 scripts/check_forbidden_claims.py
# Verify command examples:
atlas --help
# Spot-check documented commands:
atlas <documented_command> --help
```

## Output format expected

When editing docs, produce:
1. A list of claims changed or added
2. Evidence for each claim (benchmark, test, source code reference)
3. Confirmation that `check_forbidden_claims.py` passes
4. Any removed or softened marketing language

## Common failure modes to avoid

- **Credibility drift.** Over time, docs accumulate aspirational language that outpaces implementation. Periodically audit docs against actual code.
- **Mock tools described as live.** A tool registry entry with a mock implementation is not a live broker integration.
- **Benchmarks cited without artifacts.** A footnote referencing a benchmark that does not exist in the repo is misleading.
- **Missing known limitations.** Users trust release notes more when limitations are transparent.
- **Stale command examples.** A removed command still documented causes user confusion and support burden.
