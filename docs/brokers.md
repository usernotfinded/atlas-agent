# Brokers

Atlas Agent v0.5.1 uses an adapter-based architecture
 for broker integration.

## Broker Adapters
All adapters must implement the `Broker` interface (`src/atlas_agent/brokers/base.py`).

- **PaperBrokerAdapter**: A deterministic local simulator. It is the default for all runs and does not require credentials.
- **AlpacaBroker**: Live adapter for Alpaca Markets.
- **BinanceBroker**: Live adapter for Binance (Spot).
- **CCXTBroker**: A multi-exchange adapter using the CCXT library.

## Broker Sync Layer
The `BrokerSyncService` (`src/atlas_agent/brokers/sync.py`) provides provider-neutral synchronization. It pulls account equity, current positions, and active orders into the internal model, ensuring the `RiskManager` has an accurate view of current exposure.

## Mandatory Safety Rules
1.  **No Bypass**: No broker adapter may bypass the `RiskManager` or `ApprovalManager`.
2.  **Audit Logging**: Every broker interaction (orders, cancels, syncs) must be recorded in the audit hash-chain.
3.  **Live Opt-in**: Live execution is never automatic and requires explicit configuration.

