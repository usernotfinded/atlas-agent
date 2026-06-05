# Learning Suggestions

Learning suggestions are local, structured artifacts that help operators review and improve the agent's behavior over time. They are **advisory-only**, **offline**, and **never auto-executed**.

## Scope

- Learning suggestions consume local artifacts: reflections, skill candidates, approved skills, reports, backtest summaries, research artifacts, and manual notes.
- They produce structured suggestions with evidence, limitations, safety notes, and a recommended next step.
- They do not execute trades, activate skills, or call providers or brokers.

## Safety

- **Advisory-only:** `execution_policy` defaults to `advisory_only`. No automatic execution is supported.
- **Offline:** All generation uses a static fallback. `provider_execution_disabled` is `True` by default.
- **No skill auto-activation:** Suggestions may recommend creating a skill candidate, but they never activate or promote skills automatically.
- **No trading instructions:** Suggestions are framed as research-only, not financial advice, and not trading instructions.
- **No secrets:** Suggestions contain no API keys, credentials, or sensitive data.

## Status Lifecycle

```
draft -> pending_review -> accepted/rejected -> archived
```

- `draft`: Created by the generator. Editable.
- `pending_review`: Submitted by the operator for review.
- `accepted`: Operator accepts the suggestion. No automatic action is taken.
- `rejected`: Operator rejects the suggestion. Reason is required.
- `archived`: Accepted or rejected suggestions can be archived.

## CLI Usage

```bash
# Create a learning suggestion from a local file
atlas learning suggest --input path/to/artifact.md --kind report

# Create from a reflection or skill (same command, kind detected)
atlas learning suggest --input .atlas/reflections/<id>.json --kind reflection

# List suggestions
atlas learning list-suggestions
atlas learning list-suggestions --status pending_review

# Show a suggestion
atlas learning show-suggestion <suggestion-id>

# Submit for review
atlas learning submit-suggestion <suggestion-id>

# Accept or reject
atlas learning accept-suggestion <suggestion-id> --reason "looks good"
atlas learning reject-suggestion <suggestion-id> --reason "incomplete"

# Archive
atlas learning archive-suggestion <suggestion-id> --reason "stale"
```

## Storage

Suggestions are stored as JSON under `.atlas/learning/suggestions/`. They are local-only and are not staged or committed unless explicitly required.

## Provenance

Each suggestion records:
- `source_reflection_id`, `source_skill_id`, or `source_path`
- `provider_execution_disabled`: always `True`
- `static_fallback`: always `True`
- `generator_version` and `generated_at`

## Audit

Each suggestion tracks state transitions with actor, timestamp, and reason in `audit.status_transitions`.
