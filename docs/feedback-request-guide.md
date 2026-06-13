# Feedback Request Guide

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

This guide explains how to ask for feedback safely and what kind of feedback is useful.

## Who to ask

Good reviewer profiles:
- Local-first AI developers who care about safety boundaries
- Python CLI maintainers who can comment on UX and packaging
- OSS release engineering reviewers who can comment on CI gates and check scripts
- Safety/audit logging reviewers who can comment on deterministic gates and tamper-evident designs
- Trading-system engineers, framed only as paper/sandbox/safety reviewers — not as live-trading validators

Do not ask:
- People to use Atlas with real money
- People to connect real broker credentials
- People to evaluate trading signal quality or strategy profitability

## What to ask

Ask for technical feedback in these categories:
- README clarity — does a new visitor understand what Atlas is and is not?
- Install friction — does `python3.11 -m pip install -e .` work cleanly?
- CLI UX — are commands named clearly? Is help text useful?
- Safety model clarity — is it obvious what is disabled by default?
- Package distribution — does the package build and install cleanly?
- CI gates — is the quick/research/full gate structure reasonable?
- Docs navigation — can reviewers find safety boundaries, audit docs, and broker model?
- Forbidden-claim/overclaim risks — do any docs accidentally overstate readiness?
- Whether a new reviewer understands what is disabled without reading source code

## What not to ask

Do not ask for:
- Profit feedback or trading signal quality
- Real-money performance reviews
- Broker setup help for live trading
- Ways to bypass safety gates
- Autonomous trading evaluations

## Suggested communities/categories

Keep outreach generic and technically focused:
- Local-first and offline-capable developer communities
- Python CLI and packaging communities
- Open-source safety and audit-logging discussions
- Release engineering and CI best-practice forums

Frame the request as looking for "technical feedback on safety boundaries, docs, and release engineering" rather than "trading bot feedback."

## Review checklist for responders

If someone offers to review, point them to:
- [External Reviewer Walkthrough](external-reviewer-walkthrough.md) — 10–15 minute safe review path
- [Reviewer Checklist](reviewer-checklist.md) — structured checklist before trusting or recommending
- [Public FAQ](public-faq.md) — answers to common questions

Encourage reviewers to check:
1. README "What this is" and "What this is not"
2. `./scripts/release_check.sh --quick`
3. `python3.11 scripts/check_public_launch_readiness.py`
4. Protected boundaries show no diff

## How to respond to criticism

- Thank the reviewer for their time.
- Do not argue that Atlas is "actually safe" or "ready for production."
- Document valid concerns as issues or ADRs.
- If the criticism is about missing features, note the `v0.6.10` source and public-release status and link to known limitations.
- If the criticism is about safety wording, treat it as high priority and update docs promptly.

## How to handle security/safety reports

- Direct reporters to GitHub Security Advisories for private disclosure.
- Do not dismiss safety concerns as "not applicable because live trading is disabled."
- Evaluate every report for its impact on the paper/sandbox workflow and docs integrity.
- Document resolved issues in `SECURITY.md` and changelog if appropriate.

## How to triage feedback into issues

Create GitHub issues for:
- Docs clarity improvements
- Install friction reports with reproduction steps
- CI gate suggestions
- Safety wording concerns
- Missing checklist items

Do not create issues for:
- Requests to enable live trading by default
- Requests to bypass safety gates
- Profitability or trading signal evaluations
- Broker setup tutorials for real-money trading

## Safety reminder

- Live trading disabled by default.
- Provider execution remains locked.
- Trust remains blocked.
- No credentials required for default verification.
- Not financial advice. Does not imply profitability or trading correctness.
