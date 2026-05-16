# atlas-agent-audit-integrity

## When to use this skill

- Changes to `AuditWriter`, audit log format, or audit file paths
- Changes to hash-chain computation (`previous_hash`, `event_hash`)
- Changes to manifest generation or root hash verification
- Changes to event logging schema or `EventLogger`
- Changes to redaction logic that runs before audit writes
- Adding new event types

## Files and areas this applies to

- `src/atlas_agent/audit/` (AuditWriter, hash-chain, manifest)
- `src/atlas_agent/events/` (EventLogger, schema, log)
- `src/atlas_agent/redaction.py`
- `src/atlas_agent/cli.py` (event emission points)
- `audit/` workspace directory
- `events/` workspace directory

## Non-negotiable rules

1. **AuditWriter must remain separate from generic logging.** It controls append-only writes with hash-chain linking. Do not route audit records through standard loggers.
2. **Redaction must happen before hashing.** If a secret leaks into an audit record, the hash permanently binds it. Redact at the emission point.
3. **`previous_hash` must chain correctly.** A broken chain breaks tamper-evidence. When adding a new write path, ensure it reads the previous record's hash or uses the initialization hash.
4. **Manifests must include root hash verification.** Any change to manifest structure must preserve the root hash computation and verification path.
5. **Event payload keys must be bounded.** New event types must declare allowed payload keys. Never emit raw objects, exception text, or full request/response bodies in events.
6. **Event schema changes require `KNOWN_EVENT_TYPES` updates.** Add the new event type to `src/atlas_agent/events/schema.py` before emitting it.
7. **Audit and event logs must not be committed.** They are runtime artifacts. Ensure `.gitignore` covers them.

## Required checks

- [ ] New event types added to `KNOWN_EVENT_TYPES` in `src/atlas_agent/events/schema.py`
- [ ] New audit write paths use `AuditWriter` or `EventLogger`, not `print()` or standard logging
- [ ] Payloads redacted before write (no secrets, no raw exception text, no absolute paths)
- [ ] Hash-chain link preserved (previous_hash computed and stored)
- [ ] Manifest verification still passes (`atlas audit verify --all` or equivalent)

## Required tests or verification commands

```bash
python3.11 -m pytest tests/audit -q
python3.11 -m pytest tests/events -q
python3.11 -m pytest tests/ -q -k "audit or event or hash"
```

If audit tests do not exist, verify manually:

```bash
# Create a workspace and trigger an event
atlas init /tmp/atlas-audit-test --template routine-trader
cd /tmp/atlas-audit-test
atlas validate
ls audit/ events/
```

## Output format expected

When changing audit or event behavior, produce:
1. The event type(s) affected
2. Allowed payload keys for each new/modified event
3. Redaction strategy for the payload
4. Confirmation that hash-chain linking is preserved
5. Any new manifest field or verification rule

## Common failure modes to avoid

- **Emitting full objects in events.** Event payloads must be bounded dicts with scalar values and small lists. Do not dump dataclasses or full JSON bodies.
- **Forgetting `KNOWN_EVENT_TYPES`.** Event schema validation rejects unknown types, causing runtime errors.
- **Audit write without redaction.** A single unredacted secret in an audit log creates a permanent exposure.
- **Breaking manifest backward compatibility.** If manifest format changes, old manifests must still verify or be explicitly versioned.
- **Using `logging.info()` for audit records.** Standard logging lacks hash-chain guarantees and may be filtered or rotated.
