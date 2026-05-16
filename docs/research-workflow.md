# Research Workflow

## Scope

The Atlas Agent research workflow is **paper-only** and **analysis-only**. It creates local artifacts for review, not financial advice. It does not submit orders, does not create approvals, does not create pending orders, does not authorize live trading, and does not call brokers.

All commands operate on local data within the Atlas workspace. No external broker or live trading infrastructure is required.

## Command Overview

| Command | Purpose | Writes artifact | Read-only | Live trading |
|---|---|---|---|---|
| `atlas research run --symbol SYMBOL` | Create a paper-only research artifact | Yes | No | No |
| `atlas research list` | List existing research artifacts | No | Yes | No |
| `atlas research show RUN_ID` | Show a single research artifact | No | Yes | No |
| `atlas research plan RUN_ID` | Create a paper-only plan from a research artifact | Yes | No | No |
| `atlas research verify PLAN_ID` | Verify a paper plan for completeness and constraints | Yes | No | No |
| `atlas research evaluate PLAN_ID --data PATH` | Evaluate a paper plan against local data | Yes | No | No |
| `atlas research summary` | Overview of all research artifacts and plans | No | Yes | No |
| `./scripts/demo_research_workflow.sh` | End-to-end temporary-workspace demo of the full chain | Yes | No | No |

`list`, `show`, and `summary` are read-only. `run`, `plan`, `verify`, and `evaluate` write local artifacts only. None of them touch live trading.

## Typical Flow

```bash
# 1. Create a research artifact
atlas research run --symbol AAPL

# 2. List existing artifacts
atlas research list

# 3. Inspect a specific artifact
atlas research show RUN_ID

# 4. Derive a paper-only plan from the artifact
atlas research plan RUN_ID

# 5. Verify the plan for completeness and paper-only constraints
atlas research verify PLAN_ID

# 6. Evaluate the plan against local historical data
atlas research evaluate PLAN_ID --data data/sample/ohlcv.csv

# 7. Overview all research state
atlas research summary
```

What each step produces:

- `run` creates a research artifact with symbol context, thesis, risks, and invalidation conditions.
- `list` shows metadata for all research artifacts without loading full bodies.
- `show` loads and displays one research artifact.
- `plan` creates a deterministic paper-only plan derived from the research artifact.
- `verify` runs deterministic checks on the plan and creates a verification artifact.
- `evaluate` loads local CSV data and creates an evaluation artifact with data metrics.
- `summary` aggregates counts and latest IDs across all artifacts and plans.

## Artifacts

All artifacts use workspace-relative paths in CLI output and artifact fields.

### Research artifact

Saved at:

```
.atlas/research/<SYMBOL>/<run_id>.json
```

Contains: `run_id`, `symbol`, `mode`, `provider`, `summary`, `thesis`, `market_context`, `risks`, `invalidation_conditions`, `paper_only_plan`, `warnings`, `metadata`.

### Paper plan artifact

Saved at:

```
.atlas/research/<SYMBOL>/plans/<plan_id>.json
```

Contains: `plan_id`, `source_run_id`, `symbol`, `mode`, `provider`, `thesis_recap`, `constraints`, `risk_notes`, `invalidation_checks`, `paper_only_actions`, `verification_steps`, `warnings`, `metadata`.

### Verification artifact

Saved at:

```
.atlas/research/<SYMBOL>/verifications/<verification_id>.json
```

Contains: `verification_id`, `source_plan_id`, `source_run_id`, `symbol`, `mode`, `provider`, `source_plan_path`, `checks`, `passed_checks`, `failed_checks`, `recommendation`, `warnings`, `metadata`.

### Evaluation artifact

Saved at:

```
.atlas/research/<SYMBOL>/evaluations/<evaluation_id>.json
```

Contains: `evaluation_id`, `source_plan_id`, `source_run_id`, `symbol`, `mode`, `provider`, `source_plan_path`, `data_source`, `data_summary`, `checks`, `metrics`, `recommendation`, `warnings`, `metadata`.

### Path and event safety

- Artifact paths shown in CLI are workspace-relative.
- Event payloads contain safe metadata only (bounded keys like `run_id`, `symbol`, `mode`, `artifact_path`, `status`).
- Full artifact bodies are not written into event payloads.

## Command Details

### `atlas research run --symbol SYMBOL`

Creates a paper-only research artifact using the deterministic local provider.

- Paper-only mode.
- Does not call a broker.
- Supports `--json` for safe JSON envelope output.
- Supports `--provider deterministic` (default).

### `atlas research list`

Read-only discovery of existing research artifacts.

- Supports `--json`.
- Supports `--symbol` to filter.
- Supports `--limit` (default 20, max 100).
- Does not create artifacts.

### `atlas research show RUN_ID`

Read-only inspection of a single research artifact.

- Supports `--json`.
- Does not create artifacts.

### `atlas research plan RUN_ID`

Creates a deterministic paper-only plan from an existing research artifact.

- Derives constraints, risk notes, invalidation checks, and verification steps from the source artifact.
- Does not create approvals or pending orders.
- Supports `--json`.

### `atlas research verify PLAN_ID`

Verifies a paper plan for completeness and paper-only constraints.

- Runs deterministic local checks: `plan_schema_complete`, `paper_only_mode`, `no_live_authorization_language`, `has_risk_notes`, `has_invalidation_checks`, `has_verification_steps`, `has_paper_only_constraints`, `source_path_contained`.
- Creates a verification artifact.
- Recommendation values:
  - `paper_review_ready`
  - `manual_review_required`
- Does not authorize live trading.
- Supports `--json`.

### `atlas research evaluate PLAN_ID --data PATH`

Evaluates a paper plan against local CSV data.

- Requires `--data PATH` pointing to a local CSV file.
- Runs deterministic checks: `plan_loaded`, `paper_only_mode`, `data_file_loaded`, `data_has_required_columns`, `data_has_rows`, `data_symbol_context`, `plan_has_verification_steps`, `plan_has_invalidation_checks`, `no_live_authorization_language`.
- Metrics include: `row_count`, `first_date`, `last_date`, `latest_close`, `min_close`, `max_close`.
- Creates an evaluation artifact.
- Does not produce trading signals.
- Does not estimate profit.
- Recommendation values:
  - `paper_evaluation_ready`
  - `manual_review_required`
- Supports `--json`.

### `atlas research summary`

Read-only overview of all research artifacts and paper plans.

- Aggregates counts and latest IDs per symbol.
- Supports `--json`.
- Does not create artifacts.

### `./scripts/demo_research_workflow.sh`

End-to-end temporary-workspace demo of the full research chain.

- Creates a temporary workspace, runs `init`, `discipline setup`, and `config set`.
- Executes: `run` -> `list` -> `show` -> `plan` -> `verify` -> `evaluate` -> `summary`.
- Validates JSON outputs, artifact existence, workspace-relative paths, and safety invariants.
- Verifies no pending orders are created.
- Does not require broker credentials.
- Cleans up the temporary workspace unless `--keep-workspace` is used.

## JSON Output

Commands that create or inspect artifacts support `--json` where implemented. The output is a safe JSON envelope.

Generic example:

```json
{
  "ok": true,
  "status": "...",
  "symbol": "AAPL",
  "artifact_path": ".atlas/research/AAPL/..."
}
```

Rules:

- No absolute host paths should appear in output.
- No raw exceptions are exposed.
- No secrets are included.
- No broker bodies are included.

## Safety Boundaries

The research workflow never:

- calls `place_order`
- calls `resolve_execution_broker("live")`
- calls `OrderRouter.route`
- creates `ApprovalManager` pending orders
- creates approvals
- mutates `pending_orders`
- enables live trading
- requires broker credentials

## Known Limitations

- Only the deterministic/local research provider is supported.
- No LLM research provider is enabled here.
- No real broker end-to-end verification.
- Not a strategy engine.
- Not financial advice.
- Evaluation checks data availability and objective metrics; it does not assess profitability or generate trading signals.
