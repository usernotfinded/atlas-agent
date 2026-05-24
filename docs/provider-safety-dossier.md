# Provider Safety Dossier

> **Not financial advice.** This document describes a local safety-reporting workflow, not trading recommendations.

## What this is

The Provider Safety Dossier is a **local, offline safety report** for the mock provider pipeline in Atlas Agent. It consolidates the full chain of mock-response artifacts into a single tamper-evident document that can be inspected, exported, and shared for review.

It is a **proof and reporting layer**, not an execution layer. The dossier does not submit orders, call brokers, or authorize live trading. It exists so developers and reviewers can see that Atlas Agent treats provider responses with skepticism and never trusts them by default.

## What this is not

The Provider Safety Dossier is explicitly **not**:

- Live trading
- Broker execution
- Provider execution
- A trust grant
- Order approval
- Credential loading
- Network enablement
- Financial advice

Safety validation in the dossier does not imply profitability or trading correctness. It only confirms that the artifact chain was built and reviewed according to the local sandbox contract.

## Safety chain

The full chain is:

1. **`mock_response_simulation`** — Generate a deterministic mock provider response from a local prompt packet. No network, no API keys.
2. **`mock_response_import_candidate`** — Import a locally prepared provider response JSON file for review. No real provider calls.
3. **`mock_response_review_sandbox`** — Run a deterministic sandbox review of the imported response against safety rules. No trust is granted.
4. **`mock_response_trust_decision_blocker`** — Record the explicit decision to **block** trust. The response is not trusted; execution remains locked.
5. **`mock_response_final_safety_seal`** — Apply a final local safety seal over the blocked chain. The seal is tamper-evident and offline.
6. **`provider_safety_dossier`** — Consolidate the entire chain into one summary artifact with hashes, lineage, and safety verdict.
7. **`provider_safety_dossier Markdown export`** — Export the dossier to a human-readable Markdown file with redacted paths and safe sentinels.
8. **`provider_safety_dossier discovery UX`** — List, filter, and discover dossiers by status without exposing raw invalid fields or absolute paths.

## Invariants

The following hard invariants remain **false** throughout the provider safety pipeline:

| Invariant | Value |
|---|---|
| `provider_call_allowed` | `false` |
| `actual_provider_call_made` | `false` |
| `provider_response_trusted` | `false` |
| `mock_response_trusted` | `false` |
| `trading_signal_generated` | `false` |
| `approval_created` | `false` |
| `pending_order_created` | `false` |
| `broker_touched` | `false` |
| `network_enabled` | `false` |
| `credentials_loaded` | `false` |
| `trust_upgrade_performed` | `false` |
| `trust_decision_granted` | `false` |
| `provider_execution_unlocked` | `false` |
| `real_provider_response_imported` | `false` |
| `live_trading_path_enabled` | `false` |
| `broker_order_path_enabled` | `false` |

## Commands

### Discover the latest valid dossier

```bash
atlas research provider-safety-dossier-latest --json
```

Returns safe metadata for the newest valid dossier, ignoring invalid or tampered artifacts. Exposes only safe fields: `artifact_id`, `artifact_hash`, `created_at`, `provider_id`, `sandbox_only`, `chain_health`, `safety_verdict`, `export_available`, and `safe_status`.

### List dossiers with filtering

```bash
atlas research provider-safety-dossier-list --status sandbox_chain_complete --limit 5 --json
```

Supported statuses:

- `sandbox_chain_complete` — valid dossier with a complete chain
- `chain_incomplete` — valid dossier with a missing chain link
- `chain_invalid` — invalid dossier (non-tamper validation failure)
- `unsafe_tamper_detected` — hash mismatch or forbidden claim detected

### Export a dossier to Markdown

```bash
atlas research provider-safety-dossier-export <DOSSIER_ID> --format markdown --output reports/provider-safety-dossier.md
```

The export uses a safe envelope:

- `output_path_relative` — workspace-relative path only
- `output_path_redacted: true` — confirms the absolute path is hidden
- No raw invalid fields are copied
- No secrets or credential-like strings are emitted

## Safe output policy

Atlas Agent enforces a safe output policy for all provider safety dossier commands:

- **Absolute paths are redacted** or converted to workspace-relative paths.
- **Invalid or tampered artifacts use static safe sentinels** (`chain_invalid`, `unsafe_tamper_detected`) instead of raw error details.
- **Raw invalid fields are never copied** into summaries or export output.
- **Forbidden fragments** (local user paths, authorization headers, bearer tokens, broker secrets, API keys, etc.) are blocked from appearing in any output.

## Review checklist

Copy this checklist into external reviews or security assessments:

- [ ] The dossier is generated from a local mock pipeline, not from a live provider call.
- [ ] The chain includes `mock_response_simulation` or `import_candidate`, `review_sandbox`, `trust_decision_blocker`, and `final_safety_seal`.
- [ ] No step in the chain sets `provider_response_trusted = true`.
- [ ] No step in the chain creates approvals, pending orders, or trading signals.
- [ ] The export does not contain absolute paths, secrets, or credential-like strings.
- [ ] Invalid or tampered artifacts are summarized with safe sentinels, not raw error text.
- [ ] The system does not load `.env.atlas`, call brokers, or enable network access during dossier creation.
- [ ] The README and docs do not claim the system is live-trading ready, production ready, or safe to trade autonomously.

## Limitations

Be aware of the honest limitations of the Provider Safety Dossier:

- **Markdown only** — Export is Markdown. No HTML or PDF export is provided.
- **No live trading unlock** — The dossier does not and cannot enable live trading.
- **No provider execution unlock** — The dossier does not and cannot authorize real provider calls.
- **Valid complete chain required** — A complete, valid chain is required for `sandbox_chain_complete` status.
- **Artifact safety does not imply profitability or trading correctness** — The dossier validates structural safety and chain integrity, not strategy performance.
- **Sandbox-only** — The entire pipeline operates on local, deterministic mock responses. External LLM or provider calls are not part of this pipeline.
