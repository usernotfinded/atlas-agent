# Provider Integration Requirements Checklist

This checklist defines the requirements that must be met before real LLM/API provider integration is implemented. It is a **planning document**; no real provider execution exists today. Future opt-in is required before any real provider execution.

## Required Before Provider Adapter Interface

- [ ] Provider call command is disabled by default.
- [ ] No provider call can run in CI without explicit secret setup.
- [ ] Provider adapter interface (`AIProvider`) is defined and documented.
- [ ] Adapter registration is explicit; no dynamic import of arbitrary provider modules.
- [ ] Provider ID validation is strict and bounded.
- [ ] Model ID validation enforces max length and forbidden-fragment scan.

## Required Before Credential Loading

- [ ] Credential loading path is separate from research/preflight commands.
- [ ] `.env.atlas` is not loaded by any configless command.
- [ ] API keys are never stored in artifacts.
- [ ] API keys are never printed to stdout, stderr, logs, or events.
- [ ] API keys are never serialized into JSON envelopes.
- [ ] Tests prove credential loader is not called when provider is disabled.
- [ ] Provider credential boundary artifact exists documenting secret policies.
- [ ] Provider credential boundary artifact confirms all safety flags are `False`.

## Required Before First Real Network Call

- [x] Outbound payload is generated as an artifact before the network call.
- [x] Payload artifact is denylist-clean.
- [x] Payload artifact hash is computed and stored.
- [x] Payload preview artifact contains `payload_shape`, `payload_minimization_summary`, `payload_redaction_summary`, `blocked_fields`, and safe category labels only.
- [x] Payload preview artifact confirms all 25 safety flags are `False`.
- [ ] Dry-run artifact hash matches the real payload hash (parity check).
- [ ] Explicit opt-in artifact or manual unlock command has been executed.
- [ ] Provider execution state artifact documents the transition to `provider_call_allowed`.
- [ ] Audit event is logged before the request (static-safe, no secrets).
- [ ] Network call is bounded by timeout and retry limits.
- [ ] Network call does not send absolute paths, broker credentials, or raw secrets.

## Required Before Accepting Provider Response

- [ ] Provider response is stored as an untrusted artifact.
- [ ] Response is scanned for forbidden fragments.
- [ ] Response is validated against a schema.
- [ ] Response hash is computed and stored.
- [ ] Audit event is logged after the response (static-safe, no secrets).
- [ ] Response cannot bypass `review-response` validation.
- [ ] Response is marked as untrusted by default.

## Required Before Any Integration with Trading Pipeline

- [ ] Provider response cannot create orders.
- [ ] Provider response cannot approve orders.
- [ ] Provider response cannot bypass `review-response`.
- [ ] Provider response cannot call broker adapters.
- [ ] Provider output is treated as analysis-only, not as a trade signal.
- [ ] Broker/live execution boundary remains clean.

## Required Tests

- [ ] Tests prove provider calls are disabled by default.
- [ ] Tests prove provider calls fail closed when credentials are missing.
- [ ] Tests prove provider calls fail closed when provider is unknown.
- [ ] Tests prove API keys never appear in artifacts, events, logs, or CLI output.
- [ ] Tests prove outbound payloads are denylist-clean.
- [ ] Tests prove provider responses cannot create orders, approvals, or pending orders.
- [ ] Tests prove `check-artifacts` detects tampered provider execution artifacts.
- [ ] Tests prove replay detects hash drift in provider execution chain.
- [ ] Tests prove timeline correctly links provider execution artifacts.
- [ ] Tests prove no provider SDK is imported unless all gates are open.
- [ ] Tests prove no network call is made unless all gates are open.

## Required Docs

- [ ] Threat model is updated to reflect new attack surfaces.
- [ ] Provider execution policy is updated to reflect new controls.
- [ ] Integration requirements checklist is updated and signed off.
- [ ] ADR is updated if architectural decisions change.
- [ ] README is updated without overclaiming.
- [ ] CHANGELOG entry describes the new capability accurately.

## Required Manual Review Points

- [ ] Security review of outbound payload shape.
- [ ] Security review of response handling.
- [ ] Security review of credential loading path.
- [ ] Review of boundary diff for unexpected changes under `config`, `brokers`, `execution`, `safety`, `risk`.
- [ ] Review of docs for overclaiming.
- [ ] Review of tests for completeness.

## Required Rollback / Revoke Behavior

- [ ] A mechanism exists to disable provider execution globally.
- [ ] Existing opt-in artifacts can be invalidated.
- [ ] Provider execution state can be forced back to `disabled`.
- [ ] `kill-switch` mechanism covers provider execution if applicable.
- [ ] Documentation describes how to revoke provider execution.
