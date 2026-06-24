# Shadow-Live Read-Only Comparison (CAND-005)

> **Status:** implemented as a strictly read-only, fixture-first comparison layer.
> This feature does **not** implement, authorize, or enable live trading.
> `v0.6.16` remains planning-only: no source/package version bump, tag, GitHub
> Release, or PyPI publication is authorized by this documentation.
>
> **Safety banner:**
> - This is a **fixture-first**, **read-only** comparison.
> - It does **not** submit orders or call broker APIs.
> - It does **not** mutate broker state or runtime configuration.
> - It does **not** load credentials, API keys, or other secrets.
> - It does **not** call real broker APIs by default.
> - It does **not** indicate live readiness, trading safety, profitability, or permission to trade real money.
>
> **This is a read-only fixture comparison. It does not indicate live readiness, trading safety, profitability, or permission to submit orders.**
>
> **Not financial advice.** Atlas Agent is a software tool, not a financial
> advisor. Trading involves significant risk of loss. Past performance does not
> guarantee future results. No documentation here recommends any specific
> security, strategy, broker, or course of action.

## What this is

CAND-005 adds a deterministic, read-only, fixture-first comparison between Atlas's
hypothetical paper state and a recorded broker-like snapshot. It answers exactly
one question:

> Given a stateful paper run and a recorded read-only broker/account snapshot,
> what would differ between Atlas's hypothetical paper state and the
> broker-reported reality?

The comparison produces two artifacts:

- `shadow-live-comparison.json`
- `shadow-live-report.md`

CAND-005 consumes the CAND-004 trading-quality gate output as the primary paper
state source and extends it with optional richer paper artifacts (`state`,
`metrics`, `decisions`, `fills`). The broker snapshot is a local JSON fixture
only; no broker API is called, no credentials are loaded, and no orders are
submitted.

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

Options:

| Option | Required | Description |
|---|---|---|
| `--quality-gate PATH` | yes | Path to `trading-quality-gate.json` produced by CAND-004. |
| `--broker-snapshot PATH` | yes | Path to a local, read-only broker/account snapshot JSON fixture. |
| `--output-dir DIR` | yes | Directory where `shadow-live-comparison.json` and `shadow-live-report.md` are written. |
| `--state PATH` | no | Optional persisted runner-state JSON from the paper run. |
| `--metrics PATH` | no | Optional trading metrics JSON from the paper run. |
| `--decisions PATH` | no | Optional decision log in `jsonl` format. |
| `--fills PATH` | no | Optional simulated fill log in `jsonl` format. |
| `--max-snapshot-age-seconds SECONDS` | no | Maximum allowed snapshot age in seconds (default `300`). |
| `--json` | no | Emit the comparison result as JSON on stdout. |

The `atlas agent shadow-live` command:

- is a read-only fixture-first comparison,
- does not submit orders or call broker APIs,
- does not load credentials,
- does not implement live trading or live readiness.

Exit codes:

```text
0 -> matched, minor_divergence
2 -> major_divergence, stale_snapshot, incomplete_snapshot, blocked, not_evaluated
```

The CLI does not accept live-submit or credential flags such as `--live`,
`--submit`, `--broker`, `--api-key`, `--credentials`, or `--provider`.

## Local broker snapshot schema

The broker snapshot is a local JSON fixture. Its schema version is:

```text
shadow-live-snapshot.v1
```

It is modeled with the following frozen dataclasses in
`src/atlas_agent/agent/autonomous_paper_shadow_live.py`:

```python
@dataclass(frozen=True)
class BrokerPositionSnapshot:
    symbol: str
    quantity: float          # >= 0
    side: str                # "long" | "short"
    average_price: float | None
    market_price: float | None
    market_value: float | None


@dataclass(frozen=True)
class BrokerOrderSnapshot:
    order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: float          # >= 0
    filled_quantity: float   # >= 0
    limit_price: float | None
    status: str


@dataclass(frozen=True)
class BrokerFillSnapshot:
    fill_id: str
    order_id: str | None
    symbol: str
    side: str
    quantity: float          # >= 0
    price: float             # > 0
    filled_at: str


@dataclass(frozen=True)
class BrokerAccountSnapshot:
    schema_version: str                        # "shadow-live-snapshot.v1"
    account_label: str                         # redacted local label
    broker_source: str
    currency: str
    cash: float
    equity: float
    buying_power: float
    market_timestamp: str | None
    snapshot_freshness_timestamp: str
    positions: tuple[BrokerPositionSnapshot, ...]
    open_orders: tuple[BrokerOrderSnapshot, ...]
    recent_fills: tuple[BrokerFillSnapshot, ...]
    completeness_flags: dict[str, bool]
```

Validation rules:

- All numeric fields must be finite.
- Quantities and `filled_quantity` must be non-negative.
- Prices must be positive where required (`price`, `limit_price` when present).
- `quantity` is always non-negative; `side` determines sign during comparison.
- Timestamps are ISO-8601 strings, preferably UTC `Z`.
- The snapshot must not contain credentials, raw broker bodies, headers, env
  vars, or absolute paths.
- `account_label` is a redacted local label such as `paper-shadow-001`.

### Completeness flags

`completeness_flags` must include the following keys:

```json
{
  "account": true,
  "positions": true,
  "open_orders": true,
  "recent_fills": true,
  "market_prices": true
}
```

**Critical by default:**

- `account`
- `positions`
- `market_prices`

If any critical flag is missing or `false`, the comparison resolves to
`incomplete_snapshot`.

**Optional by default:**

- `open_orders`
- `recent_fills`

Optional sections being unavailable do not cause `incomplete_snapshot`. They
produce `available: false` output sections:

- If `open_orders` is `false`:
  `"open_order_differences": {"available": false, "reason": "open_orders_incomplete"}`
- If `recent_fills` is `false`:
  `"fill_differences": {"available": false, "reason": "recent_fills_incomplete"}`

## Comparison statuses

The comparison resolves to one of the following statuses, evaluated in
fail-closed hierarchy order:

1. Quality gate missing, malformed, or not `eligible_for_shadow_live_quality_review` → `blocked` or `not_evaluated`
2. Broker snapshot missing or malformed → `blocked`
3. Critical snapshot fields missing or invalid → `incomplete_snapshot`
4. Snapshot older than `--max-snapshot-age-seconds` → `stale_snapshot`
5. Divergence exceeds major thresholds → `major_divergence`
6. Divergence exceeds minor thresholds → `minor_divergence`
7. Otherwise → `matched`

Implemented statuses:

```text
matched
minor_divergence
major_divergence
stale_snapshot
incomplete_snapshot
blocked
not_evaluated
```

### Divergence thresholds

Default `ShadowLiveThresholdPolicy` values:

```text
minor_cash_pct            = 1.0
major_cash_pct            = 5.0
minor_equity_pct          = 1.0
major_equity_pct          = 5.0
minor_position_qty_abs    = 1.0
major_position_qty_abs    = 5.0
minor_position_value_pct  = 2.0
major_position_value_pct  = 10.0
max_snapshot_age_seconds  = 300
```

Percentage diffs use a guarded denominator:

```text
denominator = max(abs(broker_value), abs(paper_value), 1.0)
pct_diff    = abs(diff) / denominator * 100.0
```

Signed quantity semantics:

```text
signed_quantity = quantity if side == "long" else -quantity
quantity_difference = paper_signed_quantity - broker_signed_quantity
```

## Quality gate integration

CAND-005 consumes `trading-quality-gate.json` but does not import CAND-004
internals. The default rule is:

```text
quality_state == "eligible_for_shadow_live_quality_review"  -> reviewable
otherwise                                                    -> blocked / not_evaluated
```

The quality gate JSON is the primary source of paper metrics. Optional
`--state`, `--metrics`, `--decisions`, and `--fills` allow richer comparison
inputs. If paper-side data is insufficient, the result is `not_evaluated` or
`blocked` with a clear reason.

## Output artifacts

### `shadow-live-comparison.json`

Machine-readable comparison result:

```json
{
  "artifact_type": "shadow_live_comparison",
  "schema_version": "shadow-live-comparison.v1",
  "run_id": "...",
  "symbol": "...",
  "quality_state": "...",
  "status": "...",
  "blockers": [],
  "broker_snapshot_summary": {},
  "freshness_assessment": {},
  "divergence_results": {},
  "missing_critical_fields": [],
  "threshold_policy": {},
  "input_artifacts": {},
  "disclaimer": "This is a read-only fixture comparison. It does not indicate live readiness, trading safety, profitability, or permission to submit orders."
}
```

### `shadow-live-report.md`

Human-readable report containing:

- Safety banner
- Redacted input artifact references (basenames only)
- Quality gate state
- Broker snapshot summary
- Freshness assessment
- Divergence table
- Missing critical fields
- Final status and blocked reasons
- Read-only disclaimer

All paths are redacted to basenames. No absolute paths, usernames, env vars,
credentials, raw broker/provider bodies, headers, or stack traces are written.

## Safety boundaries

| Boundary | How it is preserved |
|---|---|
| **Fixture-first offline default** | Default implementation uses local JSON fixtures only; no network calls. |
| **No broker/provider/live execution imports** | `autonomous_paper_shadow_live.py` imports no broker, provider, or execution modules. |
| **No credential loading** | No API keys, tokens, passwords, secrets, or env-based credential access. |
| **No live order submission** | No `place_order`, `cancel_order`, `flatten_all`, `broker.submit`, `OrderRouter`, `can_submit`, or equivalent. |
| **No mutation** | Input files, runner state, and broker snapshots are read-only; mutation tests verify this. |
| **No live readiness claim** | Output artifacts and docs explicitly disclaim live readiness, safety, and profitability. |

## Relationship to other documents

- [Bounded Live Autonomy Governance](bounded-live-autonomy-governance.md)
- [Shadow-Live Readiness Contract](shadow-live-readiness-contract.md)
- [Autonomous Paper Trading Quality Gate](autonomous-paper-quality-gate.md)
- [Autonomy Roadmap](autonomy-roadmap.md)

## Reviewer checklist

- [ ] `docs/shadow-live-readonly-comparison.md` exists and clearly states the
      feature is read-only, fixture-first, and not live trading.
- [ ] The doc does not claim Atlas is ready for live, autonomous, or production
      trading, or that it eliminates risk or guarantees profit.
- [ ] The exact disclaimer is present: "This is a read-only fixture comparison.
      It does not indicate live readiness, trading safety, profitability, or
      permission to submit orders."
- [ ] `src/atlas_agent/agent/autonomous_paper_shadow_live.py` imports no
      broker, provider, or live execution code.
- [ ] No credential, secret, token, or API key loading is present.
- [ ] No `place_order`, `cancel_order`, `flatten_all`, `broker.submit`,
      `OrderRouter`, `can_submit`, `live_trading_enabled=True`, or
      `paper_only=False` patterns are present.
- [ ] All required statuses are defined and tested.
- [ ] CLI wiring adds `atlas agent shadow-live` with the required options.
- [ ] CLI help clearly states read-only / fixture-first / no live submit / no
      credential loading / no live readiness.
- [ ] Output artifacts include both JSON and Markdown reports.
- [ ] Paths are redacted to basenames; no absolute paths leak.
- [ ] Input files are not mutated by the CLI or API.
- [ ] `atlas run --mode live` remains fail-closed.

---

*CAND-005 does not change runtime behavior to enable live trading, broker order
submission, or autonomous live-trading readiness.*
