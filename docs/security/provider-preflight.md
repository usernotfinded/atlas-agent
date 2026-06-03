# Provider Preflight (Dry-Run)

## Overview

The `atlas providers preflight` command generates a local-only, dry-run provider call-plan artifact. It prepares the system for future provider execution while keeping all runtime safety locks closed.

**This is a dry-run feature only.**

## Safety Guarantees

When running `atlas providers preflight`:

- No provider call is made.
- No network is used.
- No credentials (`.env.atlas` or environment variables) are loaded.
- No broker or live trading path is touched.
- No provider SDKs (e.g., `openai`, `anthropic`) are imported.
- No pending orders or approvals are created.
- This command does **not** authorize provider execution.
- This command does **not** make provider output trusted.

## Usage

Generate a local dry-run call-plan artifact:

```bash
atlas providers preflight \
  --provider openrouter \
  --model "openrouter/auto" \
  --purpose "research-summary" \
  --max-context-chars 4000
```

To specify a custom output path:

```bash
atlas providers preflight \
  --provider anthropic \
  --model "claude-3-opus-20240229" \
  --purpose "strategy-evaluation" \
  --output artifacts/my-custom-plan.json
```

## Artifact Schema

The generated artifact is a JSON file conforming to the `provider_call_plan` schema. It contains strict metadata and safety assertions:

```json
{
  "artifact_type": "provider_call_plan",
  "schema_version": 1,
  "created_at": "2024-05-15T12:00:00Z",
  "provider_id": "openrouter",
  "model_id": "openrouter/auto",
  "purpose": "research-summary",
  "max_context_chars": 4000,
  "payload_shape": {
    "message_count_estimate": 0,
    "raw_body_stored": false,
    "body_hash_present": true
  },
  "payload_minimization_summary": {
    "raw_prompt_body_stored": false,
    "raw_request_body_stored": false,
    "raw_response_body_stored": false,
    "hashes_only": true
  },
  "payload_redaction_summary": {
    "secrets_redacted": true,
    "absolute_paths_redacted": true,
    "broker_credentials_redacted": true
  },
  "safety_flags": {
    "provider_enabled": false,
    "network_enabled": false,
    "credentials_loaded": false,
    "outbound_request_sent": false,
    "response_received": false,
    "broker_touched": false,
    "live_trading_enabled": false,
    "pending_order_created": false,
    "order_approved": false,
    "payload_body_stored": false
  },
  "request_hash": null,
  "response_hash": null,
  "metadata_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "call_authorized": false,
  "manual_review_required": true,
  "notes": [
    "Dry-run artifact only.",
    "No provider call was made.",
    "No credentials were loaded.",
    "No network was used."
  ]
}
```

## Validation Constraints

The command enforces strict boundaries on inputs:
- **`provider_id`**: 1-64 characters.
- **`model_id`**: 1-128 characters.
- **`purpose`**: 1-128 characters.
- **`max_context_chars`**: 1-200,000.

Inputs containing control characters, newlines, absolute paths, or secret-like fragments are rejected immediately to prevent payload injection or credential leakage.

## Validation

Artifacts can be validated locally using the `validate-preflight` command:

```bash
atlas providers validate-preflight <artifact_path>
```

This ensures:
- The artifact is a well-formed JSON object.
- The `artifact_type` is `provider_call_plan`.
- The `schema_version` is supported.
- All 10 safety flags are `False`.
- `call_authorized` is `False`.
- `manual_review_required` is `True`.
- Minimization fields (`raw_prompt_body_stored`, etc.) are `False`, and `hashes_only` is `True`.
- No absolute paths or secret-like fragments exist anywhere in the artifact.
- No forbidden fields (like `api_key`, `secret`, `raw_prompt`) are present.

## Evidence bundles

`atlas providers bundle-preflight <artifact_path>` creates a local audit bundle containing:

- `call-plan.json`
- `validation-report.json`
- `manifest.json`
- `sha256sums.txt`

The command validates the artifact first. It does not call providers, load credentials, use the network, touch brokers, or enable execution.

## Bundle verification

`atlas providers verify-preflight-bundle <bundle_dir>` verifies an existing evidence bundle.

It checks required files, relative-path SHA-256 sums, manifest safety state, validation report state, and the embedded call-plan artifact.

The command is local-only. It does not call providers, load credentials, use the network, touch brokers, or enable execution.

## End-to-end smoke chain

`atlas providers smoke-preflight-chain` runs the local dry-run preflight chain:

1. generate call-plan
2. validate call-plan
3. create evidence bundle
4. verify evidence bundle

The command is local-only. It does not call providers, load credentials, use the network, touch brokers, or enable execution.
