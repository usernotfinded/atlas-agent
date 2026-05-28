# Controlled Reviewer Outreach

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## Purpose

This document defines a **small-scale, controlled outreach process** for inviting 5–10 technical reviewers to examine Atlas Agent safely. The goal is to gather structured technical feedback—install friction, docs clarity, CLI UX, safety model, and release-gate structure—without creating hype, inviting unsafe behavior, or implying trading readiness.

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.
>
> Atlas is **not a live trading product** by default. Live trading is disabled by default. Provider execution remains locked. Broker execution remains blocked unless explicit opt-in gates pass. Atlas is **not production ready** for unattended or real-money trading. Atlas does not guarantee profitability or trading correctness.

## Target reviewer profile

Ideal reviewers are:

- Python CLI developers or maintainers who can evaluate code structure and safety.
- OSS release engineers who can assess check scripts, CI gates, and release automation.
- Safety/audit reviewers who can evaluate trust boundaries and default-disabled behavior.
- Technical writers who can critique docs clarity and honesty.

Reviewers **do not** need:
- Broker accounts or API credentials.
- Trading experience or domain expertise.
- Access to live markets or real money.

## What feedback is wanted

We want structured, local-first technical feedback in these areas:

- **Install friction** — does `pip install -e .` work on a clean machine?
- **Docs clarity** — is the README accurate? Is the "What this is not" section clear?
- **CLI UX** — are commands named clearly? Is help text useful?
- **Safety model** — is it obvious what is disabled by default? Are the safety gates reasonable?
- **Research workflow** — do paper-only commands work without credentials?
- **Test / release gates** — is the quick/research/full gate structure reasonable?
- **Bug reports** — reproducible defects in local-only paths.

## What feedback is out of scope

The following are **not accepted** and will be closed without action:

- Requests to bypass safety gates or approval workflows.
- Requests to enable live trading by default.
- Requests for profit guarantees or trading performance evaluations.
- Requests for trading signal quality assessment.
- Requests for real-money broker setup tutorials.
- Credential sharing or "help me connect my broker" requests.

## Safe review path

Reviewers should follow this path without credentials or network access to live providers:

1. Clone the repo.
2. Run `pip install -e .` in a fresh virtual environment.
3. Run `./scripts/release_check.sh --quick`.
4. Run `python3.11 scripts/smoke_reviewer_golden_path.py`.
5. Run `python3.11 scripts/build_release_evidence_bundle.py --skip-slow`.
6. Open feedback via the [Reviewer Feedback](https://github.com/usernotfinded/atlas-agent/issues/new?template=reviewer_feedback.yml) template.

Reviewers should **not**:
- Configure broker credentials.
- Enable live trading.
- Run provider-dependent commands that require API keys.
- Test with real money or real market data.

## What to send reviewers

Send reviewers:

- A link to this repo.
- A link to the [External Reviewer Walkthrough](external-reviewer-walkthrough.md).
- A link to the [Reviewer Checklist](reviewer-checklist.md).
- A link to the [Feedback Intake Process](feedback-intake-process.md).
- A link to the [Public FAQ](public-faq.md).
- A brief, honest description of what Atlas is and is not (see message drafts below).

Do **not** send:
- Broker setup instructions.
- Credential examples or API keys.
- Claims about profitability, performance, or real-money safety.
- Invitations to test live trading.

## How to triage responses

Use the [Feedback Triage Taxonomy](feedback-triage-taxonomy.md) to classify incoming issues:

1. Apply type, area, priority, and risk labels.
2. Mark out-of-scope requests as `status: rejected-out-of-scope`.
3. Escalate safety-sensitive reports immediately.
4. Map blocker issues to the `v0.5.8` milestone.
5. Document non-blockers as backlog.

## How to avoid overclaiming

When describing Atlas to reviewers, stick to these facts:

- Atlas is a **supervised trading workspace**, not an autonomous trading bot.
- Live trading is **disabled by default**.
- Provider execution **remains locked**.
- Broker execution **remains blocked** unless explicit opt-in gates pass.
- Atlas is **broker-neutral**; users choose their own broker and credentials.
- Atlas does **not** guarantee profitability, trading correctness, or real-money safety.
- Atlas is **not financial advice**.

Never say:
- "Safe to trade live"
- "Profitable trading system"
- "AI trading bot that makes money"
- "Production-ready live trading"
- "Unattended trading"

## How to stop outreach if safety concerns appear

If a reviewer reports a safety concern:

1. **Pause outreach** immediately. Do not invite additional reviewers until the concern is evaluated.
2. **Triage the report** using the safety-sensitive path in the taxonomy.
3. **Fix or document** the concern before resuming outreach.
4. **Update this doc** if the concern reveals a gap in the outreach process.
5. **Resume outreach** only after the fix is verified and the release check passes.

## Outreach message drafts

Use these copy-pasteable drafts when reaching out to reviewers. All drafts avoid profitability claims, live-trading readiness claims, broker setup requests, credential sharing, and safety-bypass requests.

### Short direct message

```text
Hi [name],

I'm looking for a small group of technical reviewers (5–10 people) to look at a Python CLI project I've been building. It's a supervised trading workspace with paper-mode workflows, safety gates, and audit logs—not a live trading product.

The review is completely safe: no credentials, no broker setup, no real money. reviewers run local checks in a temp workspace and share structured feedback via a GitHub issue template.

If you're interested, the repo is here: https://github.com/usernotfinded/atlas-agent

Start with the external reviewer walkthrough (10–15 min). Let me know if you have questions.

Not financial advice. Live trading is disabled by default.
```

### Longer technical review request

```text
Hi [name],

I'm preparing a small controlled review of Atlas Agent, a Python CLI framework for supervised trading workspaces. I'm inviting 5–10 technical reviewers to evaluate the codebase, docs, CLI UX, and safety model.

What Atlas is:
- A broker-neutral control layer for market research, paper trading, and risk-gated trade evaluation.
- A CLI with deterministic check scripts, audit logs, and approval queues.
- A local-first tool: no cloud dependency, no mandatory credentials.

What Atlas is not:
- Not an autonomous trading bot.
- Not a live trading product by default.
- Not financial advice.
- Not a profitability guarantee.

What I'm asking from reviewers:
- Run the install and local smoke tests on a clean machine.
- Review the README, docs, and CLI help text for clarity and honesty.
- Evaluate the safety model: what is disabled by default, what gates exist.
- Submit structured feedback via the GitHub issue template.

What reviewers should not do:
- Configure broker credentials or enable live trading.
- Evaluate trading performance or signal quality.
- Share credentials or personal financial data.

Repo: https://github.com/usernotfinded/atlas-agent
Walkthrough: docs/external-reviewer-walkthrough.md
Feedback template: GitHub Issues → Reviewer Feedback

Let me know if you're interested or have questions.
```

### GitHub/Reddit-style post

```text
[Project review] Atlas Agent — supervised trading workspace (paper-mode, safety-first)

I'm looking for 5–10 technical reviewers to evaluate a Python CLI project focused on supervised trading workflows. This is a small controlled review, not a public launch.

Key points:
- Paper-mode and research workflows work without credentials.
- Live trading is disabled by default.
- Broker execution is blocked unless explicit opt-in gates pass.
- Deterministic local check scripts verify install, CLI compatibility, and safety invariants.
- Audit logs and approval queues are built in.

What I'm looking for:
- Install friction reports
- Docs clarity feedback
- CLI UX suggestions
- Safety model critiques
- Bug reports in local-only paths

What I'm not looking for:
- Broker setup help
- Live trading enablement requests
- Profitability evaluations
- Credential sharing

If you're a Python CLI developer, OSS release engineer, or safety reviewer, check out the repo and the reviewer walkthrough. Feedback is welcome via the structured GitHub issue template.

Repo: https://github.com/usernotfinded/atlas-agent

Not financial advice. Trading involves significant risk of loss.
```

### Follow-up message

```text
Hi [name],

Thanks for agreeing to review Atlas Agent. A quick reminder of the safe review path:

1. Clone: git clone https://github.com/usernotfinded/atlas-agent.git
2. Install: cd atlas-agent && python3.11 -m venv .venv && source .venv/bin/activate && pip install -e .
3. Run checks: ./scripts/release_check.sh --quick
4. Run smoke test: python3.11 scripts/smoke_reviewer_golden_path.py
5. Open feedback: GitHub Issues → Reviewer Feedback

No credentials needed. No live trading. No real money.

If you run into any issues, include the output (with secrets and absolute paths removed) in your feedback.

Thanks again!
```

## Safety summary

- Live trading disabled by default.
- Provider execution remains locked.
- Broker execution remains blocked unless explicit opt-in gates pass.
- No credentials required for default verification.
- Not financial advice. Does not imply profitability or trading correctness.
- Outreach is controlled, small-scale, and explicitly avoids hype or overclaiming.
