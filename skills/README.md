# Atlas Agent Skills

This directory contains focused skills for AI coding agents working on Atlas Agent.

Each skill is a decision-support system, not a replacement for tests, code review, or human judgment. When in doubt, run the test suite and the release check.

## What these skills are

- **Operational guardrails** — concrete rules that reduce the chance of unsafe changes.
- **Cross-reference system** — skills link to each other so agents know when to consult multiple perspectives.
- **Living documents** — update a skill when its underlying system changes.

## What these skills are not

- A replacement for `pytest`, `git diff`, or `./scripts/release_check.sh`.
- A license to skip manual review for safety-critical changes.
- A source of truth for runtime behavior (the source code is).

## Skill index

| Skill | When to use |
|-------|-------------|
| [atlas-agent-architecture](./atlas-agent-architecture/SKILL.md) | Restructuring code, adding commands, changing imports, decomposing CLI handlers |
| [atlas-agent-security-review](./atlas-agent-security-review/SKILL.md) | Any change that touches secrets, live mode, shell execution, error output, or runtime files |
| [atlas-agent-audit-integrity](./atlas-agent-audit-integrity/SKILL.md) | Changes to audit logging, hash-chain, manifests, tamper detection, or redaction |
| [atlas-agent-broker-safety](./atlas-agent-broker-safety/SKILL.md) | Changes to broker adapters, sync, order execution, risk validation, or approval gates |
| [atlas-agent-performance](./atlas-agent-performance/SKILL.md) | Adding caches, indexes, avoiding reflection, or any claim about speed/resource usage |
| [atlas-agent-memory-backend](./atlas-agent-memory-backend/SKILL.md) | Changes to Markdown memory, SQLite index, search, rebuild-index, or snippet handling |
| [atlas-agent-release-check](./atlas-agent-release-check/SKILL.md) | Cutting a tag, bumping a version, updating changelogs, or running smoke scripts |
| [atlas-agent-docs-honesty](./atlas-agent-docs-honesty/SKILL.md) | Editing README, docs, release notes, or any user-facing copy |
| [atlas-agent-pr-review](./atlas-agent-pr-review/SKILL.md) | Reviewing a patch or PR before merge |

## Global rules

These apply to every change in Atlas Agent regardless of which skill is active.

1. **Preserve `atlas_agent.cli:main` as the CLI entrypoint.** Do not remove or rename it. Decomposition into sub-modules is allowed; the public entrypoint stays.
2. **Preserve existing CLI behavior** unless the change is explicitly required for safety. Breaking changes need justification and tests.
3. **Never weaken audit safety for performance.** Audit integrity is safety-critical.
4. **AuditWriter must remain separate from generic logging.** Hash-chain and manifest integrity depend on controlled write paths.
5. **Markdown memory remains the source of truth.** SQLite is an optional index/cache only. Every feature that reads memory must work when SQLite is absent.
6. **Strict broker sync must remain the default.** Partial or degraded broker sync must never feed live execution, risk validation, approval decisions, or order placement.
7. **Redact secrets everywhere.** Normal payloads, exception messages, provider errors, validation errors, tool errors, memory snippets, audit logs, event logs, and CLI diagnostics must never contain raw secrets.
8. **Do not commit runtime data.** `memory.sqlite`, audit logs, event logs, local state files, generated caches, and pending orders must remain in `.gitignore`.
9. **Do not claim live/production/real-time integrations where only mock contracts exist.**
10. **Do not claim performance improvements without benchmark artifacts.**
11. **Add tests for safety-critical code changes.** If a change affects risk, audit, broker, or execution paths, it needs tests.
12. **Prefer compatibility wrappers over breaking imports.** When refactoring, keep old import paths working or provide an explicit deprecation path.

## Verification command (always run)

```bash
python3.11 -m pytest -q
python3.11 -m pip check
./scripts/demo_paper_workflow.sh
git diff --check
./scripts/release_check.sh
python3.11 scripts/check_no_protected_staged.py
```

If any of these fail, stop and fix before proceeding.
