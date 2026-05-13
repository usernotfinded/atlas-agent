# Brokers

Atlas Agent v0.5.5 uses an adapter-based architecture
 for broker integration.

## Broker Adapters
All adapters must implement the `Broker` interface (`src/atlas_agent/brokers/base.py`).

- **PaperBrokerAdapter**: A deterministic local simulator. It is the default for all runs and does not require credentials. It is the only complete, production-ready adapter.
- **AlpacaBroker**: Partial live adapter for Alpaca Markets. Configuration validation and order placement are wired; account and position sync are stubbed. Not production-grade.
- **BinanceBroker**: Partial live adapter for Binance (Spot) via CCXT. Configuration validation and order placement are wired; account and position sync are stubbed. Not production-grade.
- **CCXTBroker**: Deferred/scaffolded. All methods raise a configuration error until explicitly configured. Not operational.

No broker is recommended or preferred. Users choose their own integration based on their regulatory and financial requirements.

## Broker Sync Layer
The `BrokerSyncService` (`src/atlas_agent/brokers/sync.py`) provides the provider-neutral synchronization interface. Live sync depends on adapter maturity: PaperBrokerAdapter supports full sync, while live adapters currently have stubbed account and position sync. Live risk-state integration is deferred until live adapters mature.

## Mandatory Safety Rules
1.  **No Bypass**: No broker adapter may bypass the `RiskManager` or `ApprovalManager`.
2.  **Audit Logging**: Every broker interaction (orders, cancels, syncs) must be recorded in the audit hash-chain.
3.  **Live Opt-in**: Live execution is never automatic and requires explicit configuration. Live broker support is not production-grade.

