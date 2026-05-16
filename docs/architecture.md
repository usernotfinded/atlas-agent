# Architecture

Atlas Agent v0.5.7.dev2 is a tool-driven supervised system.

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

## CLI Shape

`atlas_agent.cli:main` remains the public entry point. Low-risk commands are routed through a small command registry and shared `CLIContext`; legacy wrappers remain in place for compatibility while command handlers move out of the entrypoint incrementally.

## Shared Infrastructure

- `atlas_agent.redaction.RedactionEngine` is the shared redaction layer for audit and event payloads. It reads environment secrets once and supports explicit refresh for tests and long-running processes.
- `atlas_agent.jsonl.JsonlWriter` is the shared append-only JSONL writer for events and legacy audit JSONL.
- `read_recent_events()` uses tail-based JSONL reading so recent event views do not need to load full event files.
