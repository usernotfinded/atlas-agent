# Shadow-Live Read-Only Comparison (CAND-005)

> **Status:** implemented as a strictly read-only, fixture-first comparison layer.
> This feature does **not** implement, authorize, or enable live trading.
> `v0.6.16` remains planning-only: no source/package version bump, tag, GitHub
> Release, or PyPI publication is authorized by this documentation.

> **Not financial advice.** Atlas Agent is a software tool, not a financial
> advisor. Trading involves significant risk of loss. Past performance does not
> guarantee future results. No documentation here recommends any specific
> security, strategy, broker, or course of action.

## What this is

CAND-005 adds a deterministic, read-only fixture comparison between Atlas's
hypothetical paper state and a recorded broker-like snapshot. It answers exactly
one question:

> Given a stateful paper run and a recorded read-only broker/account snapshot,
> what would differ between Atlas's hypothetical paper state and the
> broker-reported reality?

The comparison produces two artifacts:

- `shadow-live-comparison.json`
- `shadow-live-report.md`

## What this is not

- It is **not** a live trading system.
- It does **not** enable live submit, broker order submission, or real provider
  execution.
- It does **not** load broker credentials, API keys, tokens, passwords, secrets,
  or other credentials.
- It does **not** mutate runtime configuration, runner state, or broker
  snapshots.
- It does **not** call real broker APIs by default.
- It does **not** guarantee profit, safety, or eliminated risk.
- It does **not** approve shadow-live execution; it only produces a read-only
  comparison report.

This is a read-only fixture comparison. It does not indicate live readiness,
trading safety, profitability, or permission to submit orders. It does not
submit orders or call broker APIs. It does not load credentials. It does not
implement live trading or live readiness.

## CLI usage

```bash
atlas agent shadow-live \
  --quality-gate reports/autonomous_paper_quality/trading-quality-gate.json \
  --broker-snapshot fixtures/broker-snapshot.json \
  --output-dir reports/shadow_live \
  [--state reports/autonomous_paper_state/<run>-state.json] \
  [--metrics reports/autonomous_paper/<run>-metrics.json] \
  [--decisions reports/autonomous_paper/<run>-decisions.jsonl] \
  [--fills reports/autonomous_paper/<run>-fills.jsonl] \
  [--max-snapshot-age-seconds 300] \
  [--json]
```

The `atlas agent shadow-live` command:

- is a read-only fixture-first comparison,
- does not submit orders or call broker APIs,
- does not load credentials,
- does not implement live trading or live readiness.

## Local broker snapshot schema

The broker snapshot is a local JSON fixture with the following schema version:

```text
shadow-live-snapshot.v1
```

It contains account fields, positions, open orders, recent fills, and
completeness flags. All numeric fields must be finite; quantities and filled
quantities must be non-negative; prices must be positive where required. The
snapshot must not contain credentials, raw broker bodies, headers, env vars, or
absolute paths.

## Completeness flags

Critical flags:

- `account`
- `positions`
- `market_prices`

If any critical flag is missing or `false`, the comparison resolves to
`incomplete_snapshot`.

Optional flags:

- `open_orders`
- `recent_fills`

Optional sections being unavailable do not cause `incomplete_snapshot`; they
produce `available: false` output sections.

## Comparison statuses

The comparison resolves to one of the following statuses:

```text
matched
minor_divergence
major_divergence
stale_snapshot
incomplete_snapshot
blocked
not_evaluated
```

The quality gate must be `eligible_for_shadow_live_quality_review` for a
reviewable comparison. Otherwise the result is `blocked` or `not_evaluated`.

## Quality gate integration

CAND-005 consumes `trading-quality-gate.json` but does not import CAND-004
internals. The default rule is:

```text
quality_state == "eligible_for_shadow_live_quality_review"  -> reviewable
otherwise                                                    -> blocked / not_evaluated
```

## Safety boundaries

| Boundary | How it is preserved |
|---|---|
| **No broker/provider/live execution imports** | `autonomous_paper_shadow_live.py` imports no broker, provider, or execution modules. |
| **No credential loading** | No API keys, tokens, passwords, secrets, or env-based credential access. |
| **No live order submission** | No `place_order`, `cancel_order`, `flatten_all`, `broker.submit`, `OrderRouter`, `can_submit`, or equivalent. |
| **No mutation** | Input files, runner state, and broker snapshots are read-only. |
| **Fixture-first offline default** | Default implementation uses local JSON fixtures only; no network calls. |
| **No live readiness claim** | Output artifacts and docs explicitly disclaim live readiness, safety, and profitability. |

## Relationship to other documents

- [Bounded Live Autonomy Governance](bounded-live-autonomy-governance.md)
- [Shadow-Live Readiness Contract](shadow-live-readiness-contract.md)

## Reviewer checklist

- [ ] `docs/shadow-live-readonly-comparison.md` exists and clearly states the
      feature is read-only, fixture-first, and not live trading.
- [ ] The doc does not claim Atlas is ready for live, autonomous, or production
      trading, or that it eliminates risk or guarantees profit.
- [ ] `src/atlas_agent/agent/autonomous_paper_shadow_live.py` imports no
      broker, provider, or live execution code.
- [ ] No credential, secret, token, or API key loading is present.
- [ ] No `place_order`, `cancel_order`, `flatten_all`, `broker.submit`,
      `OrderRouter`, `can_submit`, `live_trading_enabled=True`, or
      `paper_only=False` patterns are present.
- [ ] All required statuses are defined and tested.
- [ ] CLI wiring adds `atlas agent shadow-live` with the required options.
- [ ] CLI help clearly states read-only / fixture-first / no live submit.
- [ ] Output artifacts include both JSON and Markdown reports.
- [ ] Paths are redacted to basenames; no absolute paths leak.
- [ ] Input files are not mutated by the CLI or API.

---

*CAND-005 does not change runtime behavior to enable live trading, broker order
submission, or autonomous live-trading readiness.*
