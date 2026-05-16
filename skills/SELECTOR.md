# Skill Selector

Use this document to decide which skill(s) to load for a given task.

## Quick decision table

| Task keywords | Primary skill | Secondary skill(s) |
|---------------|---------------|-------------------|
| `broker`, `live`, `order`, `risk`, `sync`, `approval`, `execution`, `submit` | [atlas-agent-broker-safety](./atlas-agent-broker-safety/SKILL.md) | [atlas-agent-security-review](./atlas-agent-security-review/SKILL.md) |
| `audit`, `hash`, `manifest`, `chain`, `tamper`, `redaction`, `verify` | [atlas-agent-audit-integrity](./atlas-agent-audit-integrity/SKILL.md) | [atlas-agent-security-review](./atlas-agent-security-review/SKILL.md) |
| `secret`, `leak`, `credential`, `API key`, `env var`, `redact`, `exception`, `shell`, `subprocess` | [atlas-agent-security-review](./atlas-agent-security-review/SKILL.md) | [atlas-agent-audit-integrity](./atlas-agent-audit-integrity/SKILL.md) |
| `memory`, `sqlite`, `fts`, `index`, `search`, `markdown`, `snippet`, `rebuild` | [atlas-agent-memory-backend](./atlas-agent-memory-backend/SKILL.md) | [atlas-agent-performance](./atlas-agent-performance/SKILL.md) |
| `cache`, `jsonl`, `csv`, `reflection`, `perf`, `benchmark`, `slow`, `hot path` | [atlas-agent-performance](./atlas-agent-performance/SKILL.md) | [atlas-agent-memory-backend](./atlas-agent-memory-backend/SKILL.md) |
| `README`, `docs`, `release notes`, `changelog`, `marketing`, `claim`, `wording` | [atlas-agent-docs-honesty](./atlas-agent-docs-honesty/SKILL.md) | — |
| `release`, `tag`, `version`, `bump`, `smoke`, `clean clone`, `checklist` | [atlas-agent-release-check](./atlas-agent-release-check/SKILL.md) | [atlas-agent-docs-honesty](./atlas-agent-docs-honesty/SKILL.md) |
| `review`, `PR`, `patch`, `diff`, `merge`, `approve` | [atlas-agent-pr-review](./atlas-agent-pr-review/SKILL.md) | All relevant domain skills |
| `CLI`, `command`, `registry`, `import`, `module`, `service`, `decomposition`, `god file` | [atlas-agent-architecture](./atlas-agent-architecture/SKILL.md) | [atlas-agent-performance](./atlas-agent-performance/SKILL.md) |
| `test`, `pytest`, `coverage`, `fixture`, `mock` | Relevant domain skill + [atlas-agent-pr-review](./atlas-agent-pr-review/SKILL.md) | — |

## Decision flow

1. **Is the task about documentation or user-facing copy?**
   → Load [atlas-agent-docs-honesty](./atlas-agent-docs-honesty/SKILL.md)

2. **Is the task about cutting a release or versioning?**
   → Load [atlas-agent-release-check](./atlas-agent-release-check/SKILL.md)

3. **Is the task about reviewing someone else's code?**
   → Load [atlas-agent-pr-review](./atlas-agent-pr-review/SKILL.md) + domain skills

4. **Does the task touch broker adapters, order execution, risk validation, or live mode?**
   → Load [atlas-agent-broker-safety](./atlas-agent-broker-safety/SKILL.md)

5. **Does the task touch audit logs, hash chains, manifests, or tamper detection?**
   → Load [atlas-agent-audit-integrity](./atlas-agent-audit-integrity/SKILL.md)

6. **Does the task touch secrets, credentials, error output, or shell execution?**
   → Load [atlas-agent-security-review](./atlas-agent-security-review/SKILL.md)

7. **Does the task touch memory storage, search, or SQLite?**
   → Load [atlas-agent-memory-backend](./atlas-agent-memory-backend/SKILL.md)

8. **Does the task claim to improve performance or add caching?**
   → Load [atlas-agent-performance](./atlas-agent-performance/SKILL.md)

9. **Does the task restructure code, add CLI commands, or change module boundaries?**
   → Load [atlas-agent-architecture](./atlas-agent-architecture/SKILL.md)

10. **Multiple skills may apply.** When in doubt, load the primary skill and at least one secondary skill.
