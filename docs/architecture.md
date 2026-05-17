# Architecture

Atlas Agent v0.5.7.dev10 is a tool-driven supervised system.

## High-Level Flow

1.  **AgentLoop**: The central reasoning engine. It composes context from market data, memory, and research.
2.  **AI Provider**: Processes the context and returns tool call requests.
3.  **ToolRegistry**: Validates tool calls against cached JSON schemas and checks safety flags. Builtin specs are separated from deterministic mock implementations; mock tools are not live integrations.
4.  **RiskManager**: Deterministically validates all proposed orders against risk limits (position size, loss limits, etc.).
5.  **ApprovalManager**: Handles manual approvals for live orders or safety plans.
6.  **OrderRouter / Broker**: Routes approved orders through normalized broker adapters.
7.  **Audit / Events**: Records actions into events JSONL and the tamper-evident audit hash-chain with run manifests and root hash verification. Event and legacy audit JSONL paths share a writer; `AuditWriter` remains separate for hash-chain and manifest safety.
8.  **BrokerSyncService**: Provides the synchronization interface for account and portfolio state. Independent read-only calls are run concurrently and normalized into one auditable result. Alpaca read-only live sync is available for analysis-only mode. Live execution sync and other broker adapters (Binance, CCXT, IBKR) remain deferred until mature.
9.  **BacktestEngine**: Provides a deterministic, local-first simulation path for strategy evaluation.
10. **Memory / Market Data**: Markdown remains the human-readable memory source. An optional `memory.sqlite` index can accelerate memory search, and CSV market data is cached in memory with mtime-based invalidation while preserving the `load_bars(symbol)` API.

AI providers and models never call broker adapters or execution modules directly. Every action is routed through the **ToolRegistry** and subject to **Risk** and **Audit** gates.

## Research Workflow

The research workflow is paper-only and analysis-only. It progresses from `run` (create a research artifact), to `list`/`show` (inspect existing artifacts), to `plan` (derive a paper-only plan artifact), to `verify` (check a plan for completeness and paper-only constraints), to `evaluate` (evaluate a plan against local data), to `summary` (overview all artifacts and plans).

For a dedicated command reference with full artifact schemas and safety boundaries, see [docs/research-workflow.md](research-workflow.md).

### Commands

- **`atlas research run --symbol SYMBOL`**: Creates a local research artifact.
- **`atlas research list`**: Read-only discovery of existing artifacts. Does not create artifacts.
- **`atlas research show RUN_ID`**: Read-only inspection of a single artifact. Does not create artifacts.
- **`atlas research plan RUN_ID`**: Creates a deterministic paper-only plan from a research artifact.
- **`atlas research verify PLAN_ID`**: Verifies a paper plan for completeness, paper-only constraints, and disallowed language. Creates a verification artifact.
- **`atlas research evaluate PLAN_ID --data PATH`**: Evaluates a paper plan against local OHLCV data and creates an evaluation artifact. Paper-only; does not create orders, approvals, or pending orders.
- **`atlas research summary`**: Read-only overview of all research artifacts and paper plans. Does not create artifacts.
- **`atlas research check-artifacts`**: Read-only health check of local artifacts. Detects malformed JSON, unsupported/legacy schema versions, duplicate IDs, symbol mismatches, and unsafe paths. Does not modify artifacts.
- **`atlas research timeline`**: Read-only lineage view linking research artifacts to plans, verifications, and evaluations. Does not modify artifacts, repair lineage, or call brokers.

### Safety boundaries

The research workflow does not submit orders, does not create pending orders, does not create approvals, does not call brokers, and does not authorize live trading. The `verify` command is paper-only and does not create approvals, pending orders, or authorize live trading. The `evaluate` command is paper-only, uses local data, and does not create approvals, pending orders, or authorize live trading. The `summary` command is strictly read-only and does not create artifacts, pending orders, or approvals.

### Research artifact

Saved at `.atlas/research/<SYMBOL>/<run_id>.json` with workspace-relative artifact paths and no absolute path output.

Required fields:
- `run_id`, `symbol`, `mode`, `provider`
- `summary`, `thesis`, `market_context`
- `risks`, `invalidation_conditions`, `paper_only_plan`
- `warnings`, `metadata`, `schema_version`

Events:
- `event_type`: `research_run_created`
- Safe event metadata with bounded payload keys only; no full artifact body in event payload.

### Plan artifact

Saved at `.atlas/research/<SYMBOL>/plans/<plan_id>.json`.

Required fields:
- `plan_id`, `source_run_id`
- `symbol`, `mode`, `provider`
- `thesis_recap`
- `constraints` (includes paper-only, does not authorize live trading, does not create pending orders)
- `risk_notes`, `invalidation_checks`
- `paper_only_actions`, `verification_steps`
- `warnings`, `metadata`, `schema_version`

Events:
- `event_type`: `research_plan_created`
- Safe event metadata with bounded payload keys only.

### Verification artifact

Saved at `.atlas/research/<SYMBOL>/verifications/<verification_id>.json`.

Created by `verify` from an existing paper plan. Contains deterministic local checks:
- `plan_schema_complete`, `paper_only_mode`, `no_live_authorization_language`
- `has_risk_notes`, `has_invalidation_checks`, `has_verification_steps`
- `has_paper_only_constraints`, `source_path_contained`

Required fields:
- `verification_id`, `source_plan_id`, `source_run_id`
- `symbol`, `mode`, `provider`
- `source_plan_path`
- `checks`, `passed_checks`, `failed_checks`
- `recommendation` (`paper_review_ready` or `manual_review_required`)
- `warnings`, `metadata`, `schema_version`

Events:
- `event_type`: `research_verification_created`
- Safe event metadata with bounded payload keys only; no full verification body in event payload.

### Evaluation artifact

Saved at `.atlas/research/<SYMBOL>/evaluations/<evaluation_id>.json`.

Created by `evaluate` from an existing paper plan and local CSV data. Contains deterministic local checks:
- `plan_loaded`, `paper_only_mode`, `data_file_loaded`
- `data_has_required_columns`, `data_has_rows`, `data_symbol_context`
- `plan_has_verification_steps`, `plan_has_invalidation_checks`
- `no_live_authorization_language`

Metrics include `row_count`, `first_date`, `last_date`, `latest_close`, `min_close`, `max_close`. No buy/sell recommendation, no signal, no expected profit.

Required fields:
- `evaluation_id`, `source_plan_id`, `source_run_id`
- `symbol`, `mode`, `provider`
- `source_plan_path`, `data_source`, `data_summary`
- `checks`, `metrics`, `recommendation` (`paper_evaluation_ready` or `manual_review_required`)
- `warnings`, `metadata`, `schema_version`

Events:
- `event_type`: `research_evaluation_created`
- Safe event metadata with bounded payload keys only; no full evaluation body in event payload.

### Summary/index output

`summary` aggregates local research artifacts, paper plans, and verification artifacts per symbol. It reports counts, latest run/plan IDs, and workspace-relative paths. It is strictly read-only and does not create artifacts.

## Research Provider Layer

- A formal research provider interface exists (`ResearchProvider` protocol).
- The deterministic provider is the only enabled provider.
- A disabled LLM provider stub exists only as a fail-closed boundary.
- No real LLM, API, or network behavior is enabled in the research provider layer.
- No API keys are read by this provider layer.
- The research provider layer is separate from broker/live-submit execution.
- `atlas research providers` is a read-only discovery command that shows provider metadata without calling providers, reading API keys, or making network requests.

## CLI Shape

`atlas_agent.cli:main` remains the public entry point. Low-risk commands are routed through a small command registry and shared `CLIContext`; legacy wrappers remain in place for compatibility while command handlers move out of the entrypoint incrementally.

## Shared Infrastructure

- `atlas_agent.redaction.RedactionEngine` is the shared redaction layer for audit and event payloads. It reads environment secrets once and supports explicit refresh for tests and long-running processes.
- `atlas_agent.jsonl.JsonlWriter` is the shared append-only JSONL writer for events and legacy audit JSONL.
- `read_recent_events()` uses tail-based JSONL reading so recent event views do not need to load full event files.
