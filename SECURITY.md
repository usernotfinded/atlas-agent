# Security Policy

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## Supported Versions

| Version | Supported |
|---|---|
| 0.6.20 (main) | Yes — current source package version on main and current public GitHub release |
| 0.6.19 | Yes — historical GitHub release |
| 0.6.18 | Yes — historical GitHub release |
| 0.6.17 | Yes — historical GitHub release |
| 0.6.16 | Yes — historical GitHub release |
| 0.6.15 | Yes — historical GitHub release |
| 0.6.14 | Yes — historical GitHub release |
| 0.6.13 | Yes — historical GitHub release |
| 0.6.11 | Yes — historical GitHub release |
| 0.6.10 | Yes — historical GitHub release |
| 0.6.9 | Historical |
| 0.6.8 | Historical |
| 0.6.7 | Historical |
| 0.6.5 | Historical |
| 0.6.4 | Historical |
| 0.6.3 | Historical |
| 0.6.2 | Historical |
| 0.5.8.1 and earlier | Best-effort security guidance only |

Live trading disabled by default in all versions.

Atlas is in active development on the `main` branch. The source version on main is 0.6.20 and the current public GitHub release is v0.6.20.
The v0.6.19 release is the historical previous public GitHub release. Earlier releases are historical. Security updates are applied to the latest development line.

## Scope

This policy covers:
- Credential or secret leaks in repository artifacts
- Path or data leaks in logs, diagnostics, or CLI output
- Safety gate bypasses or risk control weaknesses
- Provider safety workflow integrity issues
- Broker execution path concerns
- Audit log tampering or hash-chain integrity issues
- Kill switch or approval gate failures

## How to Report a Vulnerability or Safety Issue

1. **Do not open a public issue** for active security or credential-leak concerns.
2. Use [GitHub Security Advisories](https://github.com/usernotfinded/atlas-agent/security/advisories) to report privately.
3. Include:
   - Affected version or commit range
   - Category (credential leak, path leak, safety gate concern, provider safety workflow, broker execution concern, or other)
   - Affected file or command
   - Impact description
   - Reproduction steps, **without secrets or real credentials**
   - Expected safe behavior

## What Not to Include Publicly

- Secrets, API keys, broker credentials, or provider credentials
- Account IDs, portfolio values, or private financial details
- Absolute paths from your local machine
- Internal network addresses or infrastructure details
- Personal data

## Expected Response Process

- Reports via GitHub Security Advisories are acknowledged within 5 business days.
- Triage determines severity and fix priority.
- Fixes are prepared on a private branch when sensitive.
- Public disclosure follows fix availability.
- No guarantees of response time; this is a community-driven project.

## Trading/Safety-Specific Concerns

Atlas is **sandbox/paper/preflight-first** by design:
- **Live trading is disabled by default.**
- **Provider execution remains locked** unless explicitly implemented in future reviewed work.
- **Trust remains blocked** in provider safety workflows.
- **No broker/order path is enabled** by provider safety workflows.
- Safety validation does **not** imply profitability or trading correctness.

If you observe behavior that contradicts these invariants (e.g., unexpected live trading enablement, provider execution unlock without explicit opt-in, or broker contact in paper mode), report it immediately.

## Out of Scope

The following are explicitly out of scope for security reports:
- Requests for trading profit guarantees
- Requests to bypass risk gates or approval workflows
- Requests to enable live trading without review
- Requests to add broker credential examples in public issues
- General trading strategy advice or performance optimization
- Feature requests not related to security or safety

## Safety Posture

Atlas Agent maintains a safe-by-default posture:
- Deterministic risk gates are hard-coded and separate from LLM reasoning.
- All live actions require explicit human confirmation.
- The kill switch provides hierarchical emergency stop modes.
- Audit logs are tamper-evident with cryptographic hash-chains.
- The dashboard is strictly read-only and does not expose secrets.
- The Telegram remote control plane is strictly opt-in, disabled by default, and requires the operator to supply their own authenticated webhook routing. It does not bypass local risk gates or human approval.

This project does **not** claim live trading readiness, production trading readiness, or safe-to-trade status. Always use paper mode until you are fully confident in your configuration.
