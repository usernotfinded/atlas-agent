# ADR-0001: Provider Execution Remains Isolated from Trading Execution

## Status

Accepted

## Context

Atlas Agent now has a complete local provider-preflight chain (research run, prompt packet, sandbox request, provider call plan, execution dry-run, execution state, audit packet, readiness report, and preflight freeze). These artifacts are created, validated, and replayed entirely locally. No real provider calls are made. No API keys are read. No network requests are sent.

The question is: when real provider execution is eventually added, how should it relate to the existing trading and broker execution pipeline?

## Decision

Future provider execution must remain **isolated** from broker/live trading execution. It must pass through explicit policy, audit, readiness, and manual opt-in gates before any outbound call is made. Provider output must be treated as analysis-only and must never directly trigger order creation, approval, or broker adapter invocation.

Specifically:

1. Provider execution and broker execution are separate pipelines.
2. Provider output is not a trade signal.
3. A human must explicitly opt in before any real provider call.
4. Every real provider call must be preceded by a dry-run, state artifact, audit packet, and readiness report.
5. All outbound payloads must be redacted, bounded, and hash-validated.
6. All provider responses must be validated, scanned, and marked untrusted by default.
7. Credentials must never appear in artifacts, logs, or CLI output.

## Consequences

- **More artifacts and checks.** The provider-preflight chain will gain additional opt-in and policy artifacts.
- **Slower integration.** Real provider execution requires manual steps and validation, not a single command.
- **Stronger safety boundary.** Isolation makes it harder for a provider response to accidentally trigger live trading.
- **Easier auditability.** Every step produces an artifact with a hash, enabling replay and drift detection.
- **Lower risk of hidden live-trading escalation.** The explicit gates make it obvious when provider execution is enabled.

## Non-Goals

- This ADR does not authorize real provider calls today.
- This ADR does not authorize broker execution.
- This ADR does not authorize trading automation.
- This ADR does not define specific provider SDKs or adapter implementations.
