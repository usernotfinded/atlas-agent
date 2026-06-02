# Provider Execution Policy

## Purpose

This document defines the policy for future LLM/API provider execution within Atlas Agent. It is a **draft policy** for a capability that is **not yet implemented**. No real provider calls are made today.

## Safety Summary

- No provider call is made.
- No API keys are read.
- No network is used.
- No provider SDKs are imported.
- No broker is touched.
- No approvals or pending orders are created.
- Future opt-in is required before any real provider execution.

## 1. Default Deny

- Provider execution is **disabled by default**.
- No command may call a provider unless explicit future opt-in conditions are met.
- The absence of an opt-in artifact is equivalent to a deny.
- Disabled provider stubs exist for architecture completeness; they do not make network calls.

## 2. Human Opt-In

- Future real provider calls require **manual user action**.
- No automatic state transition may enable provider calls.
- No artifact may self-authorize provider execution.
- A human must explicitly create an opt-in artifact or run an unlock command.

## 3. Credential Policy

- API keys must **never** be stored in artifacts.
- API keys must **never** be printed to stdout, stderr, logs, or events.
- API keys must **never** appear in CLI output, JSON envelopes, or research artifacts.
- CI must **not** require provider secrets for default test runs.
- Credential loading must be **isolated** from research and provider-preflight commands.
- `.env.atlas` must **not** be loaded by any configless research command.
- If credentials are loaded for future provider execution, the loading path must be separate, audited, and gated.
- A **provider credential boundary artifact** must exist before any future credential loading, documenting the required secret policies and confirming all safety flags are `False`.

## 4. Outbound Payload Policy

- Only **bounded, redacted, minimized** payloads may be sent.
- No raw secrets in outbound payloads.
- No absolute paths in outbound payloads.
- No broker credentials in outbound payloads.
- No unbounded prompt bodies; max context chars must be enforced.
- No hidden live-trading instructions embedded in prompts.
- A **provider outbound payload preview artifact** must exist before any future network call.
- The payload preview artifact must contain:
  - `payload_shape`: safe metadata about request family, message count estimate, and policy flags.
  - `payload_minimization_summary`: confirmation that raw text is omitted and hashes are used.
  - `payload_redaction_summary`: confirmation that secrets, paths, and broker credentials are redacted.
  - `payload_hash`: a deterministic hash of the preview (not the raw payload).
  - `blocked_fields`: safe category labels only, never raw fragments.
- The payload preview artifact must have all safety flags set to `False`, including:
  - `provider_enabled`, `network_enabled`, `credentials_loaded`, `outbound_request_sent`, `payload_body_stored`.
- No raw prompt body, raw request body, or raw response body may be stored in the preview artifact.
- The preview artifact must be denylist-clean and hash-validated.

## 5. Provider Response Policy

- Provider responses are **untrusted** by default.
- A provider response must **not** directly create trading actions.
- A provider response must go through **review and validation** before use.
- Output must be **denylist-clean**.
- Unsafe output must **fail closed** or require manual review.
- Imported provider responses are marked `imported_untrusted` and must pass review.

## 6. Trading Separation Policy

- Provider output is **not a trade signal**.
- Provider output **cannot** approve orders.
- Provider output **cannot** create pending orders.
- Provider output **cannot** call broker adapters.
- Broker and live execution remain **separate** from the provider pipeline.
- A provider response that suggests trading action must be treated as analysis-only, not instruction.

## 7. Audit Policy

Every future provider call must produce or reference:

- **Source call-plan**: the provider call plan artifact that authorized the call.
- **Dry-run artifact**: the preflight dry-run that previewed the call.
- **State artifact**: the provider execution state at the time of the call.
- **Audit packet**: the execution audit packet documenting what happened.
- **Readiness report**: the readiness report confirming chain health before the call.
- **Freeze or policy state**: either a preflight freeze or an explicit opt-in policy artifact.
- **Request hash**: hash of the exact outbound payload.
- **Response hash**: hash of the exact response body.
- **Timestamps**: before-request and after-response timestamps.
- **Static-safe event logs**: events must not contain secrets, paths, or raw response content.

## 8. Failure Policy

| Condition | Response |
|-----------|----------|
| Missing credential | Fail closed. No provider call. |
| Unknown provider | Fail closed. No provider call. |
| Unsafe payload (denylist scan fails) | Fail closed. No provider call. |
| Drifted source artifact (hash mismatch) | Fail closed. No provider call. |
| Unsafe response | Manual review required. Do not auto-accept. |
| Raw exception leakage | Release blocker. Fix before any release. |
| Tampered readiness/freeze artifact | Fail closed. `check-artifacts` detects it. |
| CI expects secrets | Fail closed. CI must remain secret-free. |

## 9. Provider Allowlist Policy

- **No provider is enabled by default.**
- Provider IDs must be explicit and bounded.
- Model IDs remain raw user-visible strings but are validated for length and forbidden fragments.
- No provider catalog overclaiming: documentation must not imply support for providers that are not implemented.
- Future adapters must implement a defined `AIProvider` interface.
- Adapters not on the allowlist must fail closed.

## 10. Provider Response Schema Contract Policy

- **No provider response is interpreted without a recorded schema contract.**
- Schema contract artifacts are local-only and configless.
- Schema contract defines allowed response fields, rejected response fields, and validation rules.
- Manual review gate is **closed by default** and cannot be opened automatically.
- Schema contract does not make any provider response trusted.
- No raw response body, raw prompt body, or raw request body is stored in the schema contract.
- Forbidden fragments are rejected, not redacted, in schema contract content.

## 11. Provider Response Review Result Policy

- Review result contract artifacts are local-only and configless.
- Review result contract defines how a future manual review result must be recorded, bounded, redacted, validated, and kept non-authorizing.
- **No review result is present in this batch.** Missing future response artifact is expected.
- Manual review gate remains **closed**. No review result can open it.
- Review result does **not** make any provider response trusted.
- Review result does **not** authorize trading, order creation, order approval, or broker calls.
- No raw review notes, raw response body, or raw prompt body is stored in the review result.
- Trust upgrade is **not implemented** and cannot be triggered by a review result.
- Forbidden fragments are rejected, not redacted, in review result content.

## 12. Release Gate Policy

- The **full release gate** (`scripts/release_check.sh --full`) remains required before any push or tag.
- Provider integration requires **new focused gates**:
  - Tests that prove provider calls are disabled by default.
  - Tests that prove API keys do not leak.
  - Tests that prove provider responses cannot create orders.
  - Tests that prove outbound payloads are denylist-clean.
  - Tests that prove schema contract manual review gate is closed.
- Tests that prove review result contract manual review gate is closed.
- Tests that prove review result cannot make response trusted.
- Tests that prove review result cannot authorize trading.
- CI must remain **secret-free by default**.
- Documentation must be updated to reflect new capabilities **without overclaiming**.

## 13. Preflight Dry-Run Policy

- The `atlas providers preflight` command must remain purely a local dry-run feature.
- It must generate a local call-plan artifact with all safety flags set to `false`.
- It must **not** make network calls, read API keys, load `.env.atlas`, or touch broker paths.
- It does **not** authorize any actual provider execution.
- See [Provider Preflight](provider-preflight.md) for full usage and schema details.
