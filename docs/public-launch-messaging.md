# Public Launch Messaging

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

This document contains safe, copy-pasteable messaging drafts for asking public feedback. These are drafts only. Do not post them. Do not claim they were posted.

## Positioning statement

Atlas Agent is a local-first, sandbox/paper/preflight research workbench for experimenting with trading-agent safety, deterministic gates, auditability, and release-engineering checks. It is not a live-trading-ready product, not a production trading system, and not financial advice.

## One-sentence description

A local-first Python CLI workbench for paper-only trading research, deterministic safety gates, and audit trails — live trading disabled by default, provider execution remains locked, trust remains blocked.

## Short GitHub README-style summary

Atlas Agent is a broker-neutral supervised workspace for paper and sandbox trading research. It provides deterministic backtesting, provider-neutral research artifacts, tamper-evident audit logs, and deterministic risk gates. Live trading is disabled by default. Provider execution remains locked. No credentials are required for default verification. Not financial advice.

## Short Reddit/Discord feedback request

Hi — I’m working on Atlas Agent, a local-first Python CLI workbench for paper/sandbox trading research with deterministic safety gates and audit logs. The latest stable public GitHub release is v0.6.21; v0.6.20 and earlier releases are historical. It is not a live trading product.

I’m looking for feedback on:
- The safety model and what is disabled by default
- CLI UX and documentation clarity
- Release gates and CI design
- Whether the repo is understandable to a new technical reviewer

Live trading is disabled by default. Provider execution remains locked. No real-money trading is supported without explicit multi-factor opt-in. Not financial advice.

If you have time to skim the README and run `./scripts/release_check.sh --quick`, I’d appreciate any notes.

## Longer technical feedback request

Atlas Agent (v0.6.21 public; v0.6.20 historical) is a local-first, sandbox/paper/preflight research workbench for trading-agent safety, deterministic gates, auditability, and release-engineering checks. I’m looking for technical feedback before any broader public visibility.

Specific areas where feedback would help:
- README clarity: does the "What this is" / "What this is not" framing make sense?
- Install friction: does `python3.11 -m pip install -e .` and `atlas validate` work for you?
- Safety model: are the disabled-by-default boundaries clearly explained?
- CI gates: does the quick/research/full gate structure seem reasonable?
- Docs navigation: can you find the safety boundaries, audit docs, and broker model?
- Forbidden claims: do any docs accidentally overclaim readiness or profitability?

What I am not asking for:
- Profit feedback or trading signal quality
- Real-money performance reviews
- Broker setup help
- Ways to bypass safety gates

Live trading is disabled by default. Provider execution remains locked. Trust remains blocked. No credentials required for default verification. Not financial advice. Does not imply profitability or trading correctness.

## Hacker News-style "Show HN" draft

Show HN: Atlas Agent — a local-first sandbox workbench for trading-agent safety research

Atlas Agent is a Python CLI workbench for deterministic backtesting, paper-only research workflows, and audit-trail generation. It is explicitly not a live trading bot: live trading is disabled by default, provider execution remains locked, and broker order submission is blocked by `can_submit=false`.

I built it to experiment with safety-gated agentic workflows: deterministic risk limits, approval queues, kill switches, and tamper-evident audit logs. Everything runs locally without credentials for the default verification path.

I’m looking for feedback on the safety model, CLI design, docs clarity, and whether the repo structure is approachable to a new reviewer. Not financial advice.

## Direct reviewer message draft

Hi,

I’d appreciate a technical review of Atlas Agent (v0.6.21 public; v0.6.20 historical), a local-first sandbox/paper research workbench for trading-agent safety and deterministic gates.

Safe review path (10–15 minutes):
1. Skim README.md — check "What this is" and "What this is not"
2. Run `./scripts/release_check.sh --quick`
3. Run `python3.11 scripts/check_public_launch_readiness.py`
4. Check `docs/external-reviewer-walkthrough.md` for more commands

What to look for:
- Any accidental live-trading readiness claims
- Any profit or performance guarantees
- Any request for real credentials in default flows
- Any diff in protected boundaries (`src/atlas_agent/config`, `brokers`, `execution`, `safety`, `risk`)

Live trading is disabled by default. Provider execution remains locked. Trust remains blocked. Not financial advice. Does not imply profitability or trading correctness.

## What feedback to ask for

- README and docs clarity
- Install friction and Python environment issues
- CLI UX and command naming
- Safety model clarity and boundary documentation
- CI/release gate design
- Whether a new reviewer understands what is disabled
- Any overclaiming or forbidden claims in docs

## What not to claim

Do not claim or imply:
- Live trading readiness
- Production trading readiness
- Profitability or performance guarantees
- Autonomous trading capability
- Real-money safety
- Provider execution is enabled
- Broker execution is enabled
- The project is a finished product

## Safety limitations

- Live trading is disabled by default and requires explicit multi-factor opt-in.
- Provider execution remains locked — no real LLM/provider calls are made by default.
- Broker order submission is blocked by `can_submit=false`.
- Credentials are not loaded unless explicitly configured.
- Trust remains blocked — mock responses in safety workflows are explicitly not trusted.
- Not financial advice. Does not imply profitability or trading correctness.

## Current stable status

v0.6.21 is the latest stable public GitHub release and v0.6.20 and earlier releases are historical. It is ready for public review and technical feedback, but it is not a live-trading-ready product. See [Public Launch Readiness](public-launch-readiness.md) for the full verified-checks list.
