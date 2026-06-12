# Brokers

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

Atlas Agent v0.6.9 uses an adapter-based architecture for broker integration.

See also: [Broker Roadmap and Guarded Adapter Status](broker-roadmap.md) for the
authoritative support inventory, fail-closed behavior, and CLI usage.

## Broker Adapters
All adapters must implement the `Broker` interface (`src/atlas_agent/brokers/base.py`).

- **PaperBrokerAdapter**: A deterministic local simulator. It is the default for all runs and does not require credentials. It is the only fully implemented adapter; all other adapters are partial, deferred, or placeholder.
- **AlpacaBrokerAdapter**: Read-only live sync adapter for Alpaca Markets. Supports account state, positions, open orders, and balances via HTTP GET. Live order submission remains disabled (`can_submit=false`). Not production-grade for execution.
- **AlpacaBroker**: Legacy live adapter scaffold for Alpaca order placement. Configuration validation is wired, but execution is gated by `BrokerResolver`.
- **BinanceBroker**: Partial live adapter for Binance (Spot) via CCXT. Configuration validation and order placement are wired; account and position sync are deferred. Not production-grade.
- **CCXTBroker**: Deferred/scaffolded. All methods raise a configuration error until explicitly configured. Not operational.
- **IBKRStub**: Placeholder only. No fake live implementation is provided. Any access raises `NotImplementedError`.

No broker is recommended or preferred. Users choose their own integration based on their regulatory and financial requirements.

## Broker Support Inventory

The static support inventory in `src/atlas_agent/brokers/status.py` documents
the current status of every broker adapter:

| Broker | Status | Paper | Read-only sync | Live submit |
|---|---|---|---|---|
| PaperBroker | `default_paper` | ✅ | ✅ | ❌ |
| Alpaca | `supported_opt_in` | ❌ | ✅ | ✅* |
| Binance | `partial` | ❌ | ❌ | ❌ |
| CCXT (generic) | `disabled` | ❌ | ❌ | ❌ |
| Interactive Brokers (IBKR) | `placeholder` | ❌ | ❌ | ❌ |

\* Requires explicit opt-in, credentials, kill-switch normal, live mode, and a
valid opt-in record.

## Broker Sync Layer
The `BrokerSyncService` (`src/atlas_agent/brokers/sync.py`) provides the provider-neutral synchronization interface.

- **PaperBrokerAdapter**: Supports full sync (account, positions, orders, balances).
- **AlpacaBrokerAdapter**: Supports read-only live sync (account, positions, open orders, balances). Requires `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`.
- **Binance/CCXT/IBKR**: Sync remains deferred until adapters mature.

Live risk-state integration is available for Alpaca analysis-only mode. Live execution integration remains deferred.

## Mandatory Safety Rules
1.  **No Bypass**: No broker adapter may bypass the `RiskManager` or `ApprovalManager`.
2.  **Audit Logging**: Every broker interaction (orders, cancels, syncs) must be recorded in the audit hash-chain.
3.  **Live Opt-in**: Live execution is never automatic and requires explicit configuration. Live broker support is not production-grade.
4.  **Fail Closed**: Unsupported, disabled, and placeholder brokers are blocked by `BrokerResolver` and `guard_submit()` / `guard_sync()`.
