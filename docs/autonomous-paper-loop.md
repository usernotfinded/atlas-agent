# Autonomous Paper Decision Loop (CAND-001)

> **Status:** planning and design only. This document describes a proposed
> capability, not a shipped feature or a guarantee of future behavior.
>
> **Not financial advice.** Atlas Agent is a software tool, not a financial
> advisor. Trading involves risk of loss. Past performance does not guarantee
> future results.
>
> This document does **not** claim autonomous live trading readiness. It does
> not authorize, enable, or describe unsupervised live trading.

## Overview

The Autonomous Paper Decision Loop is a deterministic, paper-only, local-first
routine that evaluates market data, runs strategy logic, and records proposed
orders without contacting a broker or executing real trades. It is intended as a
sandbox for exploring bounded autonomy: the loop may iterate automatically, but
it remains confined to paper mode, uses only local or sample data, and never
submits orders to a live broker.

Key properties:

- **Deterministic replay:** Given the same configuration, sample data, and seed,
  the loop is designed to produce the same decisions on every run.
- **Paper-only:** All outcomes are simulated. No real money is at risk and no
  live positions are created.
- **Local-first:** The loop runs locally and does not require network calls to
  providers or brokers. Optional provider calls are gated behind explicit,
  reviewable configuration and are not required for the core loop.
- **Risk-gated:** Every proposed order is routed through `RiskManager` in paper
  mode. Orders that violate configured limits are rejected and logged.
- **Audit-friendly:** Each cycle produces timestamped decision records and a
  manifest for later inspection.

This is a research and sandbox tool, not a step toward unsupervised live trading.

## CLI usage

The loop is invoked through the `atlas agent autonomous-paper` subcommand. All
flags are optional and default to conservative paper-mode values.

Run up to five cycles and emit JSON results:

```bash
atlas agent autonomous-paper --max-cycles 5 --json
```

Run with a specific demo symbol and strategy:

```bash
atlas agent autonomous-paper --symbol DEMO-SYMBOL --strategy buy_and_hold --max-cycles 10
```

Write evidence artifacts to a custom directory:

```bash
atlas agent autonomous-paper --evidence-dir artifacts/autonomous_paper_evidence
```

The command defaults to paper mode, uses sample data when no feed is
configured, and fails closed if any live-trading setting is detected.

## Safety boundaries

The following boundaries are intrinsic to the design and must remain true in any
implementation:

- **Paper-only.** The loop produces simulated decisions only.
- **No live trading.** The loop does not execute real trades.
- **No live submit.** The loop never sets `can_submit=true` for live broker
  submission.
- **No broker order submission.** Broker adapters are not invoked for order
  placement.
- **No real provider calls by default.** The loop can run entirely offline; any
  provider integration is optional and explicitly configured.
- **No credentials required.** The base loop uses sample data and local
  configuration only.
- **Every proposed order routed through `RiskManager` in paper mode.** Risk
  limits are enforced independently of strategy or provider output.
- **Deterministic replay.** Identical inputs produce identical outputs.
- **No profit or safety claims.** The loop does not guarantee returns, eliminate
  risk, or claim readiness for live deployment.

## Artifact format

Each run writes two artifacts under `reports/autonomous_paper/` (or the
`--evidence-dir` override):

- `<run_id>-decisions.jsonl` — one JSON object per cycle containing the cycle
  index, timestamp, symbol, signal, proposed order (if any), `RiskManager`
  result, and rejection reason when applicable.
- `<run_id>-manifest.json` — run metadata including the command-line invocation,
  configuration snapshot, data source, cycle count, and hashes of the decision
  file for tamper-evidence checks.

Both files are local, redacted, and intended for offline review and audit.

## Relationship to other documents

- [Bounded Live Autonomy Governance](bounded-live-autonomy-governance.md) —
  explains why autonomous live trading remains disabled, opt-in, and
  governance-gated.
- [Shadow Live Readiness Contract](shadow-live-readiness-contract.md) — defines
  the observability and safety contract any future live-readiness shadow loop
  must satisfy.

---

*This document is part of the `CAND-001` planning line. It does not change
runtime behavior, enable live trading, or claim autonomous live-trading
readiness.*
