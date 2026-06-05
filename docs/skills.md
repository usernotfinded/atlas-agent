# Skills

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## Skill Candidates

Skill candidates are structured, reviewable artifacts derived from reflection artifacts or local research/report/backtest artifacts. They are **not active behavior**.

### Key properties

- **Local-only**: All candidate artifacts are stored under `.atlas/skill_candidates/` as JSON files.
- **Offline**: No provider APIs, broker APIs, or network services are called during generation.
- **Research-only**: Candidates are framed as operational notes, not trading instructions.
- **Not automatically active**: `activation_policy` defaults to `manual_only`.
- **Human review required**: A candidate must be explicitly approved before it can be promoted to the skill library.

### Lifecycle

```text
draft -> pending_review -> approved -> promoted -> (skill library)
                     \-> rejected -> archived
```

1. **Create**: `atlas skills create-candidate --input <path> [--kind <kind>]`
2. **Submit**: `atlas skills submit-candidate <candidate-id>`
3. **Approve / Reject**: `atlas skills approve-candidate <candidate-id>` / `atlas skills reject-candidate <candidate-id> --reason "..."`
4. **Promote**: `atlas skills promote-candidate <candidate-id>` (only if approved)
5. **Archive**: `atlas skills archive-candidate <candidate-id>`

### CLI commands

```bash
atlas skills create-candidate --input <path> --kind reflection --dry-run
atlas skills list-candidates [--status <status>] [--json]
atlas skills show-candidate <candidate-id> [--json]
atlas skills submit-candidate <candidate-id>
atlas skills approve-candidate <candidate-id> [--reason "..."]
atlas skills reject-candidate <candidate-id> --reason "..."
atlas skills archive-candidate <candidate-id> [--reason "..."]
atlas skills promote-candidate <candidate-id>
atlas skills list-library [--json]
atlas skills show-library <skill-id> [--json]
```

### Safety

- Provider execution is disabled by default.
- Broker execution is disabled by default.
- Live trading is disabled by default.
- No secrets are read or printed.
- Missing data is shown explicitly.
- No fake content is invented.
- No profit guarantees or financial advice claims.

## Skill Library

The skill library contains promoted skills under `.atlas/skills/library/`. These are structured JSON artifacts with provenance, limitations, and safety notes. They remain offline and require manual activation.

## Existing Markdown-Based Skills

Atlas Agent also maintains a legacy markdown-based skill system under `skills/active/`, `skills/proposed/`, and `skills/archived/`. The new candidate foundation does not replace this system; it adds a structured artifact layer on top.
