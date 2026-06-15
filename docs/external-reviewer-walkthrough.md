# External Reviewer Walkthrough

> **Not financial advice.** Atlas Agent is a software tool, not a financial
> advisor. Trading involves significant risk of loss.

This page orients external technical reviewers. The runnable command sequence
lives in the [Reviewer Golden-Path Validation Guide](reviewer-golden-path.md);
this walkthrough intentionally does not maintain a second copy.

## Start here

1. Follow the [Reviewer Golden-Path Validation Guide](reviewer-golden-path.md).
2. Use the [Paper-Trading Guide](paper-trading-guide.md) only when you want the
   manual setup path and annotated fail-closed configuration.
3. Use [Broker and Provider Preflight Diagnostics](preflight-diagnostics.md)
   for the read-only `atlas doctor` field and redaction contract.
4. Read [Demo: Paper Workflow](demo-paper-workflow.md) for expected output and
   the [Demo Artifact Index](demo-artifact-index.md) for generated local files.

The canonical demo command is `./scripts/demo_paper_workflow.sh`. The
[Demo Proof Checker](../scripts/check_demo_proof.py) and
[Demo Command Smoke Checker](../scripts/check_demo_command_smoke.py) validate
the documented surface without contacting providers or brokers.

## Review boundary

The canonical path is local, deterministic, paper-only, and fail-closed:

- no credentials required;
- no provider, broker, exchange, or remote API calls;
- no order submission or live-submit enablement;
- live trading disabled by default;
- provider execution remains locked;
- trust remains blocked.

Atlas is not a broker, financial advisor, autonomous trading system, or
assurance of future outcomes. Historical and simulated results do not predict
future performance.

## Repository areas to inspect

- `README.md` for positioning, current release status, and the short quickstart.
- `SECURITY.md` and `CONTRIBUTING.md` for reporting and contribution boundaries.
- `docs/reviewer-checklist.md` for a structured review checklist.
- `src/atlas_agent/risk/` and `src/atlas_agent/safety/` for deterministic gates.
- `src/atlas_agent/brokers/` for adapter boundaries.

Do not infer live-trading readiness from the presence of broker adapters. Live
trading remains disabled unless every explicit config, credential, risk,
approval, kill-switch, audit, manifest, and opt-in requirement is satisfied.

## Reporting findings

- Security or safety issues: use
  [GitHub Security Advisories](https://github.com/usernotfinded/atlas-agent/security/advisories).
- Bugs: use the bug report issue template.
- Documentation issues: use the docs issue template.
- General feedback: use the feature request template or a discussion.
