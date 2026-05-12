# Architecture

Atlas Agent v0.5.3 is a tool-driven autonomous system.

## High-Level Flow

1.  **AgentLoop**: The central reasoning engine. It composes context from market data, memory, and research.
2.  **AI Provider**: Processes the context and returns tool call requests.
3.  **ToolRegistry**: Validates tool calls against JSON schemas and checks safety flags.
4.  **RiskManager**: Deterministically validates all proposed orders against risk limits (position size, loss limits, etc.).
5.  **ApprovalManager**: Handles manual approvals for live orders or safety plans.
6.  **OrderRouter / Broker**: Executes approved orders through normalized broker adapters.
7.  **Audit / Events**: Records every action into a tamper-evident hash-chain with run manifests and root hash verification.
8.  **BrokerSyncService**: Synchronizes account and portfolio state from the broker back into the internal model.
9.  **BacktestEngine**: Provides a deterministic, local-first simulation path for strategy evaluation.

AI providers and models never call broker adapters or execution modules directly. Every action is routed through the **ToolRegistry** and subject to **Risk** and **Audit** gates.

