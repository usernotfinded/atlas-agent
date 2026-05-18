# Research Workflow

## Scope

The Atlas Agent research workflow is **paper-only** and **analysis-only**. It creates local artifacts for review, not financial advice. It does not submit orders, does not create approvals, does not create pending orders, does not authorize live trading, and does not call brokers.

All commands operate on local data within the Atlas workspace. No external broker or live trading infrastructure is required.

## Research Providers

The enabled research provider is `deterministic`.

- `deterministic` is a local provider and does not make network or API calls.
- Unsupported providers fail closed; there is no silent fallback.
- LLM and external research providers are not enabled in this tag.
- The disabled LLM provider stub does not call APIs, read API keys, or use external services.
- Provider selection does not authorize live trading.
- Provider selection does not create approvals or pending orders.
- Provider output remains paper-only and analysis-only.
- Provider output is stored as local research artifacts only.
- No broker credentials are required.

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
| `atlas research check-artifacts` | Read-only health check of local artifacts | No | Yes | No |
| `atlas research timeline` | Read-only lineage/timeline of artifact relationships | No | Yes | No |
| `atlas research providers` | Read-only discovery of available research providers | No | Yes | No |
| `atlas research prompt RUN_ID` | Generate a sanitized prompt packet from a research artifact | Yes | No | No |
| `atlas research sandbox PROMPT_PACKET_ID` | Build a local LLM sandbox request artifact from a prompt packet | Yes | No | No |
| `atlas research simulate-provider PROMPT_PACKET_ID` | Simulate a deterministic provider response from a prompt packet | Yes | No | No |
| `atlas research review-response PROVIDER_RESPONSE_ID` | Review a provider response artifact deterministically | Yes | No | No |
| `atlas research dossier RUN_ID` | Build a deterministic dossier consolidating a research chain | Yes | No | No |

`list`, `show`, `summary`, `check-artifacts`, `timeline`, and `providers` are read-only. `run`, `plan`, `verify`, `evaluate`, `prompt`, `simulate-provider`, `review-response`, and `dossier` write local artifacts only. None of them touch live trading.

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
- `prompt` creates a sanitized, bounded prompt packet artifact for future provider work.
- `sandbox` creates a bounded, local, replayable LLM sandbox request artifact from a prompt packet. No LLM is called. No network request is made. No API key is read.
- `simulate-provider` creates a deterministic mock provider response artifact from a prompt packet.
- `review-response` creates a deterministic response review artifact from a provider response artifact.
- `dossier` creates a deterministic summary artifact consolidating the full research chain.

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

### Prompt packet artifact

Saved at:

```
.atlas/research/<SYMBOL>/prompts/<prompt_packet_id>.json
```

Contains: `prompt_packet_id`, `source_run_id`, `symbol`, `mode`, `provider`, `source_artifact_path`, `max_context_chars`, `system_boundary`, `user_context`, `allowed_uses`, `forbidden_uses`, `redaction_summary`, `warnings`, `metadata`.

### Sandbox request artifact

Saved at:

```
.atlas/research/<SYMBOL>/sandbox_requests/<sandbox_request_id>.json
```

Created by `sandbox` from an existing prompt packet artifact. Contains a bounded, local, replayable LLM sandbox request:
- `request_payload`: sanitized, redacted, bounded input derived from the prompt packet.
- `system_boundary`: explicit flags (`paper_only`, `analysis_only`, `no_trading_advice`, `no_live_trading_authorization`, `no_broker_submit`, `no_pending_orders`, `no_approvals`, `no_api_network_call`, `no_financial_advice`, `no_trading_signal_generation`).
- `explicit_boundaries`: human-readable statements that no LLM provider is called, no network request is made, no API key is read, no broker is contacted, no order is generated, no approval is created, and no live trading is authorized.
- `redaction_summary`: safe counts only (`redacted_fragments_count`, `truncated`).
- Lineage fields (`sandbox_request_id`, `prompt_packet_id`, `source_run_id`) are validated before artifact creation. Tampered lineage causes the command to fail closed with no artifact written and no unsafe value leaked.
- Does not call LLMs.
- Does not call APIs or network.
- Does not read API keys.
- Does not submit orders.
- Does not create approvals or pending orders.
- Does not authorize live trading.

### Provider response artifact

Saved at:

```
.atlas/research/<SYMBOL>/provider_responses/<provider_response_id>.json
```

### Response review artifact

Saved at:

```
.atlas/research/<SYMBOL>/response_reviews/<response_review_id>.json
```

Created by `review-response` from an existing provider response artifact. Contains a deterministic local review:
- `checks`: deterministic checks for provider response validity, schema support, paper-only mode, simulated provider, present source IDs, valid symbol, response sections/summary presence, safety checks presence, no disallowed language, no secret fragments, response boundedness, and source path containment.
- `recommendation`: `provider_response_review_ready` or `manual_review_required`.
- `redaction_summary`: safe counts only (`redacted_fragments_count`).

Contains: `provider_response_id`, `source_prompt_packet_id`, `source_run_id`, `symbol`, `mode`, `provider`, `provider_status`, `source_prompt_packet_path`, `response_summary`, `response_sections`, `safety_checks`, `passed_checks`, `failed_checks`, `recommendation`, `redaction_summary`, `warnings`, `metadata`.

### Dossier artifact

Saved at:

```
.atlas/research/<SYMBOL>/dossiers/<dossier_id>.json
```

Created by `dossier` from an existing research run. Consolidates the paper-only research chain into one bounded, safe summary artifact:
- `workflow_status`: presence flags for research, plans, verifications, evaluations, prompts, provider responses, and response reviews.
- `artifact_counts`: counts of each linked artifact type.
- `linked_artifacts`: relative paths and IDs of linked artifacts.
- `summaries`: bounded, sanitized summaries of each artifact type.
- `safety_summary`: local-only, no-network, no-api-keys, paper-only flags.
- `missing_links`: safe static codes for missing artifact types.
- `recommendation`: `research_dossier_ready` or `manual_review_required`.
- Does not call LLMs, APIs, or network.
- Does not read API keys.
- Does not submit orders or create approvals/pending orders.
- Does not authorize live trading.
- Output is for paper review only.

Contains: `dossier_id`, `source_run_id`, `symbol`, `mode`, `provider`, `source_research_path`, `workflow_status`, `artifact_counts`, `linked_artifacts`, `summaries`, `safety_summary`, `missing_links`, `warnings`, `recommendation`, `redaction_summary`, `metadata`.

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

### `atlas research check-artifacts`

Read-only health check of local research artifacts.

- Detects: malformed JSON, unsupported schema versions, legacy artifacts without `schema_version`, duplicate IDs, symbol mismatches, unsafe paths, missing required fields, and unexpected artifact locations.
- Supports `--symbol` to filter by symbol.
- Supports `--strict` to exit with code 2 when issues are found.
- Does not modify, migrate, or rewrite artifacts.
- Does not create pending orders or approvals.

### `atlas research providers`

Read-only discovery of available research providers.

- Shows which providers are available, disabled, local, networked, and whether they require credentials.
- `deterministic` is shown as available, enabled, default, local, and does not require an API key.
- LLM/external providers are shown as disabled.
- Does not call providers.
- Does not read API keys.
- Does not make network calls.
- Does not modify config.
- Does not authorize live trading.
- Supports `--json`.

### `atlas research prompt RUN_ID`

Generate a sanitized, bounded prompt packet artifact from an existing research artifact.

- Loads an existing research artifact by `run_id`.
- Produces a prompt packet under `.atlas/research/<SYMBOL>/prompts/<prompt_packet_id>.json`.
- Includes bounded `user_context` (symbol, summary, thesis, market context, risks, invalidation conditions, paper-only plan, citations) useful for future LLM research provider work.
- `system_boundary` explicitly states: paper-only, analysis-only, no trading advice, no live trading authorization, no broker submit, no pending orders, no approvals, no API/network call required.
- `allowed_uses` and `forbidden_uses` constrain how the packet may be used.
- Redacts unsafe fragments: absolute paths, secrets, API keys, Bearer tokens, auth headers, `sk-` tokens, APCA markers, broker hosts.
- `redaction_summary` reports safe counts only (`redacted_fragments_count`, `truncated`).
- Supports `--max-context-chars` (default: 8000, maximum: 20000). Invalid values fail closed.
- Does not call LLMs.
- Does not call network.
- Does not read API keys.
- Does not submit orders.
- Does not create approvals or pending orders.
- Does not authorize live trading.
- Does not modify source research artifacts.
- Supports `--json`.

### `atlas research sandbox PROMPT_PACKET_ID`

Build a bounded, local, replayable LLM sandbox request artifact from an existing prompt packet.

- Loads an existing prompt packet by `prompt_packet_id`.
- Produces a sandbox request artifact under `.atlas/research/<SYMBOL>/sandbox_requests/<sandbox_request_id>.json`.
- Validates copied lineage fields (`prompt_packet_id`, `source_run_id`, `symbol`) before constructing output or writing artifacts.
- Tampered or unsafe lineage values fail closed; no artifact is written and no unsafe value is leaked in CLI output.
- Redacts unsafe fragments: absolute paths, secrets, API keys, Bearer tokens, auth headers, `sk-` tokens, APCA markers, broker hosts.
- `redaction_summary` reports safe counts only (`redacted_fragments_count`, `truncated`).
- Does not call LLMs.
- Does not call APIs or network.
- Does not read API keys.
- Does not submit orders.
- Does not create approvals or pending orders.
- Does not authorize live trading.
- Supports `--json`.

### `atlas research simulate-provider PROMPT_PACKET_ID`

Simulate a deterministic provider response from an existing prompt packet artifact.

- Loads an existing prompt packet by `prompt_packet_id`.
- Produces a provider response artifact under `.atlas/research/<SYMBOL>/provider_responses/<provider_response_id>.json`.
- Only `deterministic-mock` provider is supported. Unsupported providers fail closed.
- Generates bounded response sections: `scope_review`, `context_summary`, `risk_review`, `invalidation_review`, `paper_only_review`, `follow_up_questions`.
- Runs deterministic safety checks: `prompt_packet_loaded`, `prompt_schema_supported`, `paper_only_mode`, `provider_is_simulated`, `no_network_provider`, `no_api_key_required`, `no_live_authorization_language`, `no_order_language`, `no_financial_advice_language`, `no_secret_fragments`, `response_bounded`, `source_path_contained`.
- Redacts unsafe fragments from response content if safety checks fail.
- Recommendation values:
  - `provider_response_review_ready`
  - `manual_review_required`
- Does not call LLMs.
- Does not call APIs or network.
- Does not read API keys.
- Does not submit orders.
- Does not create approvals or pending orders.
- Does not authorize live trading.
- Does not modify source prompt packet artifacts.
- Supports `--json` and `--provider deterministic-mock`.

### `atlas research dossier RUN_ID`

Build a deterministic dossier consolidating a research chain.

- Loads an existing research artifact by `run_id`.
- Inspects linked local artifacts: plans, verifications, evaluations, prompt packets, provider responses, response reviews.
- Produces a dossier artifact under `.atlas/research/<SYMBOL>/dossiers/<dossier_id>.json`.
- `workflow_status` summarizes presence of each artifact type.
- `artifact_counts` counts linked artifacts.
- `linked_artifacts` lists relative paths only.
- `summaries` are bounded and sanitized.
- `safety_summary` confirms local-only, no-network, no-api-keys, paper-only.
- `missing_links` lists safe static codes for missing types.
- Recommendation values:
  - `research_dossier_ready`
  - `manual_review_required`
- Does not call LLMs.
- Does not call APIs or network.
- Does not read API keys.
- Does not submit orders.
- Does not create approvals or pending orders.
- Does not authorize live trading.
- Does not modify source research artifacts.
- Supports `--json` and `--include-artifact-index`.

### `./scripts/demo_research_workflow.sh`

End-to-end temporary-workspace demo of the full research chain.

- Creates a temporary workspace, runs `init`, `discipline setup`, and `config set`.
- Executes: `run` -> `list` -> `show` -> `plan` -> `verify` -> `evaluate` -> `summary` -> `check-artifacts` -> `timeline` -> `providers` -> `prompt` -> `sandbox` -> `simulate-provider` -> `review-response` -> `dossier`.
- Validates JSON outputs, artifact existence, workspace-relative paths, artifact health checks, lineage/timeline reconstruction, and safety invariants.
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

## Artifact Schema Versioning

New research workflow artifacts include `schema_version`. The current schema version is `1`.

- All newly written artifacts include `"schema_version": "1"` as a top-level field.
- Older artifacts without `schema_version` are treated as legacy where possible; `show`, `plan`, `verify`, and `evaluate` continue to load them.
- Unsupported future schema versions fail closed for commands that need to load full artifacts (`show`, `plan`, `verify`, `evaluate`).
- `list` and `summary` skip artifacts with unsupported schema versions safely.
- Atlas does not silently rewrite old artifacts in this batch.

## Known Limitations

- Only the deterministic/local research provider is supported.
- No LLM research provider is enabled here.
- No real broker end-to-end verification.
- Not a strategy engine.
- Not financial advice.
- Evaluation checks data availability and objective metrics; it does not assess profitability or generate trading signals.
