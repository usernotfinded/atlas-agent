# Atlas Agent Reflection Artifacts

Reflection artifacts are structured local records that analyze input artifacts
(reports, backtests, research, audit summaries, manual notes). They are safe,
offline, and require operator review before downstream use.

## Scope

- Reflections use only files already present in the workspace.
- Reflections do **not** call provider APIs by default.
- Reflections do **not** call broker APIs.
- Reflections do **not** use the network.
- Reflections do **not** contain fake, placeholder, or invented data.
- Reflections are deterministic and safe to run offline.

## Status Lifecycle

```
draft -> submit -> pending_review -> approve -> approved -> archive -> archived
                                 -> reject -> rejected -> archive -> archived
```

Only `pending_review` reflections can be approved or rejected.
Only `approved` or `rejected` reflections can be archived.

## CLI Commands

```bash
# Create a reflection from a local file (static fallback, no provider call)
atlas reflection create --input reports/daily-report-2026-06-05.md --kind report --json

# List reflections
atlas reflection list --json

# Show a reflection
atlas reflection show <REFLECTION_ID> --json

# Submit for review
atlas reflection submit <REFLECTION_ID>

# Approve
atlas reflection approve <REFLECTION_ID> --reason "looks good"

# Reject
atlas reflection reject <REFLECTION_ID> --reason "incomplete data"

# Archive
atlas reflection archive <REFLECTION_ID> --reason "old"
```

## Static Fallback

When provider execution is disabled (the default), the generator produces a
structured static reflection that clearly marks:

```json
{
  "provider_execution_disabled": true,
  "static_fallback": true
}
```

No fake insights are generated. Observations are structural (line counts,
section presence) and review questions are generic and safe.

## Output Schema

Each reflection artifact includes:

- **reflection_id** — UUID
- **status** — draft | pending_review | approved | rejected | archived
- **provenance** — generator version, timestamps, input artifact reference, hash
- **audit** — status transitions, reviewer identity, timestamps
- **output** — summary, observations, questions, provider_disabled flag
- **disclaimer** — research-only, not financial advice

## Storage

Reflection artifacts are stored as JSON files under:

```text
.atlas/reflections/
```

Generated artifacts are local-only and must not be staged.

## Safety

- Reflections remain local, offline, and research-only.
- No financial advice is given.
- No profit or performance guarantees are made.
- No secrets are printed.
- Operator review is required before any downstream use.
