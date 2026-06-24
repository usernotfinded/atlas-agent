# CAND-005 Design: Shadow-Live Read-Only Comparison

> **Status:** design spec — candidate implementation plan.  
> **Candidate:** CAND-005  
> **Version target:** v0.6.16 (planning-only; no source/package version bump, tag, release, or PyPI publication).  
> **Date:** 2026-06-23

## What this is

CAND-005 adds a strictly read-only, fixture-first shadow-live comparison layer to Atlas Agent.

It answers exactly one question:

> Given a stateful paper run and a recorded read-only broker/account snapshot, what would differ between Atlas’s hypothetical paper state and the broker-reported reality?

It does **not** answer:

> Can Atlas submit live orders?  
> Is Atlas live-ready?  
> Is Atlas profitable?  
> Can Atlas safely trade real money unattended?

## What this is not

- It is **not** a live trading system.
- It does **not** enable live submit, broker order submission, or real provider execution.
- It does **not** load broker credentials, API keys, or other secrets.
- It does **not** mutate runtime configuration, runner state, or broker snapshots.
- It does **not** call real broker APIs by default.
- It does **not** guarantee profit, safety, or eliminated risk.
- It does **not** approve shadow-live execution; it only produces a read-only comparison report.

## Architecture

Single focused module:

- `src/atlas_agent/agent/autonomous_paper_shadow_live.py`

Public API:

- `build_shadow_live_comparison(...)` → deterministic comparison `dict`
- `write_shadow_live_artifacts(report, output_dir)` → writes JSON and Markdown artifacts

Data flow:

1. CLI receives `--quality-gate`, `--broker-snapshot`, `--output-dir`, optional paper artifact overrides (`--state`, `--metrics`, `--decisions`, `--fills`), and `--max-snapshot-age-seconds`.
2. Loader parses `trading-quality-gate.json` and `broker-snapshot.json` with strict JSON validation.
3. Quality gate state is checked first. Only `eligible_for_shadow_live_quality_review` allows reviewable comparison.
4. Snapshot is validated for required fields, finite numeric values, freshness, and completeness flags.
5. Comparison engine diffs paper state against the broker snapshot:
   - cash, equity, buying power
   - positions (signed quantity diff, market value diff)
   - open orders
   - recent fills (if both sides complete)
   - missing critical fields
6. Status resolver combines quality gate result, staleness, completeness, and divergence severity into a final status.
7. Writers emit `shadow-live-comparison.json` and `shadow-live-report.md` with redacted paths and a read-only disclaimer.

## Local broker snapshot schema

Frozen dataclasses inside `autonomous_paper_shadow_live.py`:

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

Required `completeness_flags`:

```json
{
  "account": true,
  "positions": true,
  "open_orders": true,
  "recent_fills": true,
  "market_prices": true
}
```

Rules:

- No credentials, raw broker bodies, headers, env vars, or absolute paths.
- `account_label` is a redacted local label (e.g., `paper-shadow-001`).
- Numeric fields must be finite; quantities and filled quantities non-negative; prices positive where required.
- Timestamps are ISO-8601 strings, preferably UTC `Z`.
- `quantity` is always non-negative; `side` determines sign during comparison.

## Comparison engine and statuses

Internal signed quantity:

```text
signed_quantity = quantity if side == "long" else -quantity
quantity_difference = paper_signed_quantity - broker_signed_quantity
```

Outputs:

- `cash_difference`
- `equity_difference`
- `buying_power_difference` (with `available: false` if paper value unavailable)
- `position_differences`
- `open_order_differences`
- `fill_differences` (only if both sides complete)
- `missing_critical_fields`
- `stale_snapshot`

Divergence thresholds (serialized as `ShadowLiveThresholdPolicy`):

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

Statuses (fail-closed hierarchy):

1. Quality gate missing/malformed/not `eligible_for_shadow_live_quality_review` → `blocked` or `not_evaluated`
2. Broker snapshot missing/malformed → `blocked`
3. Required snapshot fields missing/invalid → `incomplete_snapshot`
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

## Quality gate integration

CAND-005 consumes `trading-quality-gate.json` but does not import CAND-004 internals.

Default rule:

```text
quality_state == "eligible_for_shadow_live_quality_review"  → reviewable
otherwise                                                    → blocked / not_evaluated
```

The quality gate JSON is also the primary source of paper metrics. Optional `--state`, `--metrics`, `--decisions`, `--fills` allow richer comparison inputs. If paper-side data is insufficient, return `not_evaluated` or `blocked` with a clear reason.

## CLI

Command:

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

Help text must state:

```text
read-only fixture-first comparison
does not submit orders or call broker APIs
does not load credentials
does not implement live trading or live readiness
```

Exit codes:

```text
0 -> matched, minor_divergence
2 -> major_divergence, stale_snapshot, incomplete_snapshot, blocked, not_evaluated
```

CLI must not accept live-submit or credential flags (`--live`, `--submit`, `--broker`, `--api-key`, `--credentials`, `--provider`).

## Artifacts

`shadow-live-comparison.json`:

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

`shadow-live-report.md`:

- Safety banner
- Redacted input artifact references
- Quality gate state
- Broker snapshot summary
- Freshness assessment
- Divergence table
- Missing critical fields
- Final status and blocked reasons
- Read-only disclaimer

All paths are redacted to basenames. No absolute paths, usernames, env vars, credentials, raw broker/provider bodies, headers, or stack traces.

## Safety boundaries

| Boundary | How it is preserved |
|---|---|
| **No broker/provider/live execution imports** | `autonomous_paper_shadow_live.py` imports no broker, provider, or execution modules. |
| **No credential loading** | No API keys, tokens, passwords, secrets, or env-based credential access. |
| **No live order submission** | No `place_order`, `cancel_order`, `flatten_all`, `broker.submit`, `OrderRouter`, `can_submit`, or equivalent. |
| **No mutation** | Input files, runner state, and broker snapshots are read-only; mutation tests verify this. |
| **Fixture-first offline default** | Default implementation uses local JSON fixtures only; no network calls. |
| **No live readiness claim** | Output artifacts and docs explicitly disclaim live readiness, safety, and profitability. |

## Testing

New tests:

- `tests/test_shadow_live_readonly.py` — feature tests
- `tests/test_shadow_live_readonly_contract.py` — contract checker tests

Coverage:

- valid comparison generation
- missing/blocked/low-threshold quality gate blocks
- malformed quality gate/snapshot fail closed
- stale/incomplete snapshot statuses
- matched, minor, major divergence
- paper-only and broker-only positions
- open order divergence
- missing critical fields
- JSON/Markdown artifact writing
- absolute path redaction
- input file mutation tests (hashes unchanged)
- CLI smoke and help
- CLI rejects unknown live-submit/credential flags
- no broker/provider/live imports
- `atlas run --mode live` remains fail-closed (regression)

New checker:

- `scripts/check_shadow_live_readonly_contract.py`
  - source/test/doc existence
  - CLI wiring
  - required statuses present
  - required artifact names documented
  - read-only disclaimers present
  - forbidden imports/usages absent
  - forbidden claims absent

Wired into `scripts/dev_check.sh` and `scripts/release_check.sh`.

## Documentation

Add/update:

- `docs/shadow-live-readonly-comparison.md` — main CAND-005 doc
- `docs/shadow-live-readiness-contract.md` — clarify CAND-005 implemented, CAND-006 future planning
- `docs/bounded-live-autonomy-governance.md` — add CAND-005 stage
- `docs/autonomy-roadmap.md` — mark CAND-005 implemented, CAND-006 future gated submit rehearsal
- `docs/releases/v0.6.16-candidates.json`
- `docs/releases/v0.6.16-candidates.md`
- `docs/releases/v0.6.16-candidate-selection.md`
- `docs/releases/v0.6.16-plan.md`
- `CHANGELOG.md` — add CAND-005 under `[Unreleased]`

CAND-004 doc cleanup: add note that `cost_impact_pct` is an approximation/proxy for directional paper-run review, not high-precision production cost analysis.

## Release policy

- `v0.6.15` remains the current public release.
- `v0.6.16` remains candidate/planning work.
- No source/package version bump unless an existing checker requires metadata-only consistency.
- No tag, GitHub release, or PyPI publication.

## Reviewer checklist

- [ ] Module imports no broker, provider, or live execution code.
- [ ] No credential, secret, token, or API key loading.
- [ ] No `place_order`, `cancel_order`, `flatten_all`, `broker.submit`, `OrderRouter`, `can_submit`, `live_trading_enabled=True`, or `paper_only=False` patterns.
- [ ] All required statuses are defined and tested.
- [ ] CLI wiring adds `atlas agent shadow-live` with the required options.
- [ ] CLI help clearly states read-only / fixture-first / no live submit.
- [ ] Output artifacts include both JSON and Markdown reports.
- [ ] Paths are redacted to basenames; no absolute paths leak.
- [ ] Input files are not mutated by the CLI or API.
- [ ] Docs do not claim live readiness, profitability, or eliminated risk.
- [ ] `atlas run --mode live` remains fail-closed.
