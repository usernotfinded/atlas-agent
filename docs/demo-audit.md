# Demo: Audit Verification

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

Atlas Agent writes a tamper-evident audit trail for every run. This demo shows how to verify the integrity of that trail.

## What is audited

Every agent run produces:

- `audit/events.jsonl` — a hash-chained event log.
- `audit/manifests/<run_id>.json` — a run-level manifest with root-hash verification.

Default behavior stores **hashes and metadata**, not raw text:

- User objectives are stored as `prompt_hash` (SHA-256).
- Provider responses are stored as `response_hash` (SHA-256) plus `length` and `provider`.

Raw prompt and provider text logging is **opt-in** and disabled by default. To enable it, set in `.atlas/config.toml`:

```toml
[audit]
log_raw_prompts = true
log_provider_text = true
```

Even when enabled, secrets are redacted from payloads before they are written.

## Verifying the audit trail

### Verify all manifests

```bash
atlas audit verify --all
```

Expected behavior when valid:

- Atlas lists each manifest and marks it valid.
- Exit code is `0`.

If a manifest fails, Atlas reports the failure with a reason such as a hash mismatch, and the exit code is `2`.

### Verify a specific audit log

```bash
atlas audit verify
```

This checks the default `audit/events.jsonl` hash-chain directly.

Expected behavior when valid:

- Atlas reports the number of events checked and confirms the chain is intact.
- Exit code is `0`.

If the chain is broken, Atlas reports the failure and the exit code is `2`.

## What the hash-chain protects against

- **Payload tampering**: changing any event breaks its hash.
- **Tail deletion**: removing events from the end breaks the manifest root hash.
- **Manifest tampering**: the root hash is computed from the manifest contents themselves.

## What to verify

1. `audit/events.jsonl` exists and is append-only.
2. `audit/manifests/` contains `.json` files matching run IDs in the log.
3. Running `atlas audit verify --all` returns exit code `0`.
4. No raw API keys appear in either file.

## Limitations

The audit system is **tamper-evident**; it detects modification after the fact but cannot stop a malicious actor with filesystem access from deleting the entire `audit/` directory.
