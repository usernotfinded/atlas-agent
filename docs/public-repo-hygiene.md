# Public Repository Hygiene

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## Why Strict Issue and PR Templates

Atlas Agent is a real trading framework. Safety is not optional. Strict templates help contributors:
- Avoid accidentally posting secrets or credentials
- Remember to check protected boundaries
- Respect the safe-by-default design
- Keep discussions focused and actionable

## Safety Boundaries

The following areas are protected and require explicit justification to change:
- `src/atlas_agent/config` — configuration and secret handling
- `src/atlas_agent/brokers` — broker adapters and communication
- `src/atlas_agent/execution` — order execution paths
- `src/atlas_agent/safety` — safety controls and kill switch
- `src/atlas_agent/risk` — risk gates and limits

Always check:

```bash
git diff -- src/atlas_agent/config src/atlas_agent/brokers src/atlas_agent/execution src/atlas_agent/safety src/atlas_agent/risk
git diff --cached -- src/atlas_agent/config src/atlas_agent/brokers src/atlas_agent/execution src/atlas_agent/safety src/atlas_agent/risk
```

Expected: no output.

## What Is Acceptable to Report Publicly

- Bug reports with safe reproduction steps (no credentials)
- Documentation improvements
- Feature requests that respect safety boundaries
- Safety concerns that do not involve active credential leaks
- General questions about paper/sandbox workflows

## What Must Not Be Posted Publicly

- Secrets, API keys, or broker credentials
- Provider credentials or account IDs
- Personal financial details or portfolio values
- Absolute paths from your local machine
- Internal infrastructure details

## Current Release Status

Atlas is currently at public release `v0.6.13` (tagged and published on GitHub),
with `v0.6.12` as the historical previous public release:
- **Package version on `main`:** `0.6.13`
- **Latest public tag:** `v0.6.13`
- **Previous public release:** `v0.6.12`
- **Next planned release:** `v0.6.14`
- Sandbox/paper/preflight positioning
- Live trading disabled by default
- Provider execution remains locked
- Trust remains blocked
- No broker/order path in provider safety workflows
- No credentials required for docs or safety checks

## How CI Gates Protect the Project

- **Quick gate** (every PR): version consistency, forbidden claims, public docs checks, focused pytest, pip check
- **Research gate** (path-filtered or manual): research tests and sandbox validation
- **Heavy gate** (manual/tags only): full pytest, demo workflows, release checks

No CI workflow publishes, uploads, tags, or pushes.

## How Contributors Can Help

- Improve documentation and tests
- Enhance CLI UX and developer experience
- Strengthen safety validation
- Improve package and release engineering
- Add non-execution research artifacts
- Review PRs for safety boundary compliance

Thank you for keeping Atlas Agent safe by default.
