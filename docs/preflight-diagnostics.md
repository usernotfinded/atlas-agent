# Broker and Provider Preflight Diagnostics

`atlas doctor` reports local broker and provider configuration readiness without
contacting any external service or enabling execution.

```bash
atlas doctor
atlas doctor --json
```

The report covers:

- configured provider and model IDs;
- provider credential presence or absence;
- configured broker support status;
- broker credential presence or absence;
- missing optional local dependencies such as `ccxt`;
- live-trading and live-submit config flags;
- paper-only availability and local remediation hints.

## Safety Limits

The command is strictly read-only and deterministic:

- no provider, broker, exchange, or remote API calls;
- no connectivity or credential validation requests;
- no provider or submit-capable broker client construction;
- no orders, sync operations, approvals, or audit artifacts;
- no config, secret, workspace, or safety-state changes;
- risk controls, approval gates, kill-switch behavior, HMAC approval, manifests,
  and the audit chain remain unchanged.

Credential values are never printed, serialized, snapshotted, or logged. The
report includes only environment-variable names, presence state, a coarse local
format category, and `[REDACTED]` for present values. It does not reveal secret
prefixes, suffixes, lengths, or contents.

`network_check: skipped` means exactly that: the command did not test
connectivity. A `configured` result confirms only that required local settings
are present. It does not authorize provider execution or broker execution.

`live_execution_blocked: true` describes the diagnostic boundary. The command
never enables or authorizes live trading. Runtime live execution remains subject
to all existing config, credential, risk, approval, kill-switch, opt-in, audit,
and manifest gates.

Paper mode remains the safe default.
