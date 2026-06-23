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

## Stateful execution-neutral kernel (CAND-003)

> **Status:** implemented in planning. CAND-003 extends the paper-only CAND-001
> design with a reusable, execution-neutral trading kernel and a stateful paper
> runner. It is still paper-only and does not enable, authorize, or describe live
> trading.

The execution-neutral kernel separates **signal generation** from **fill
simulation**. A strategy or routine emits orders exactly as before; the kernel
applies a deterministic, configurable fill model so that the same decision logic
can be replayed, resumed, and measured without touching a broker or a provider.

Key properties:

- **Execution-neutral:** Strategy code does not know how fills are computed. The
  kernel translates orders into simulated fills using next-bar semantics and
  configurable cost assumptions.
- **Stateful:** Portfolio state (cash, positions, last-processed bar timestamp,
  order/fill history) is persisted to `--state-dir`. A restarted run can
  `--resume` from the last saved bar instead of reprocessing history.
- **Duplicate-prevention:** The runner records the last-processed bar timestamp
  and skips bars that have already been processed, so resuming does not replay
  fills or double-count PnL.
- **Configurable costs:** `--commission-bps` and `--slippage-bps` let operators
  model explicit transaction costs. `--fill-timing` selects the next-bar open,
  close, or a conservative worst-case fill.
- **Honest metrics:** The runner reports realized PnL, total return, Sharpe,
  max drawdown, win/loss counts, and other trading metrics computed only from
  simulated fills. These are paper-only estimates, not live performance
  guarantees.

### CLI options for the stateful paper runner

The CAND-003 runner accepts the following options in addition to the standard
paper-mode defaults. All flags are optional and default to conservative,
paper-only values:

- `--state-dir PATH` — directory where portfolio state, last-processed bar,
  fills, and metrics are persisted. Defaults to a local path under
  `state/autonomous_paper/`.
- `--resume` — load existing state from `--state-dir` and continue from the
  next unprocessed bar. Without this flag the runner starts fresh.
- `--initial-cash AMOUNT` — starting cash for a fresh run. Ignored when
  `--resume` loads an existing portfolio.
- `--commission-bps BPS` — commission in basis points applied to each fill's
  notional value. Defaults to a conservative non-zero value.
- `--slippage-bps BPS` — slippage in basis points applied to each fill's price.
  Defaults to a conservative non-zero value.
- `--fill-timing {open,close,vwap,worst}` — fill price assumption for the next
  bar. `worst` picks the price least favorable to the order side. `vwap` uses a
  synthetic volume-weighted estimate derived from the local bar.

Example fresh run with explicit costs:

```bash
atlas agent autonomous-paper \
  --state-dir state/demo-kernel \
  --initial-cash 100000 \
  --commission-bps 10 \
  --slippage-bps 5 \
  --fill-timing worst \
  --max-cycles 20
```

Example resuming an existing state:

```bash
atlas agent autonomous-paper \
  --state-dir state/demo-kernel \
  --resume \
  --max-cycles 10
```

### Next-bar fill semantics

The kernel is intentionally simple and conservative:

1. At the end of bar `t` the strategy evaluates bar `t` and emits any orders.
2. Orders are filled at bar `t+1` using the price selected by `--fill-timing`.
3. Commission and slippage are deducted from the fill proceeds according to
   `--commission-bps` and `--slippage-bps`.
4. Cash and position balances are updated; a fill record is appended.
5. The last-processed bar timestamp is updated to `t+1` so a resumed run will
   not reprocess the same bar.

This model makes no claim about real market liquidity, latency, or execution
quality. It is a local simulation boundary, not a live-trading promise.

### Trading metrics produced

After each run (and incrementally on resume) the kernel writes trading metrics
to the state directory. These are computed solely from simulated fills and
remain paper-only:

- Total return and cumulative PnL.
- Annualized return (when enough bars are available).
- Volatility and Sharpe ratio using local returns.
- Maximum drawdown and drawdown duration.
- Win/loss trade counts, win rate, average winner, average loser.
- Profit factor and expectancy estimates.
- Commission and slippage totals.

Metrics are written in JSON and Markdown formats. They are intended for offline
review, scorecard evaluation, and honest comparison across strategy variants.

### CAND-003 safety boundaries

The stateful runner preserves every CAND-001 boundary and adds no live-trading
capability:

- **Paper-only.** All fills are simulated; no real money is at risk.
- **No live trading.** `--mode live` is rejected; live trading is not enabled.
- **No live submit.** `can_submit` remains `false`; no broker order submission
  occurs.
- **No broker order submission.** Broker adapters are not invoked for placement,
  sync, or account state.
- **No real provider calls.** The runner is local-first and does not call AI
  providers or data providers.
- **No credentials required.** State is loaded from local files; no API keys or
  broker credentials are read.
- **Not shadow-live.** Resume and state persistence are for paper replay only;
  they do not mirror or shadow a live account.
- **Not live-ready.** Configurable costs and next-bar fills are research models,
  not evidence that the system is ready for real-money execution.
- **Not financial advice.** Simulated metrics do not guarantee future
  performance.
- **Deterministic replay.** With the same data, config, seed, and fill settings,
  the kernel produces the same sequence of fills and metrics.

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

*This document is part of the `CAND-001` and `CAND-003` planning lines. It does
not change runtime behavior, enable live trading, or claim autonomous
live-trading readiness.*
