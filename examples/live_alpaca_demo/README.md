# Live Alpaca Demo

**DANGER:** Live trading involves real financial risk. This demo is for educational purposes only. Live broker support is not production-grade.

## Safety Model
Live mode in Atlas Agent v0.5.5 is never enabled by default.
 It requires:
1.  **Explicit Configuration**: `TRADING_MODE=live` and `ENABLE_LIVE_TRADING=true`.
2.  **Manual Approval**: By default, every order requires manual approval via `atlas approve-order`.
3.  **Broker Sync**: `atlas broker sync` is the intended workflow for alignment. Live sync is deferred until adapter maturity improves.

## Setup
Configure your credentials in `.env.atlas`:
```bash
ALPACA_API_KEY=YOUR_ALPACA_KEY
ALPACA_SECRET_KEY=YOUR_ALPACA_SECRET
ALPACA_ENDPOINT_MODE=paper
```

## Running
Live submit is currently gated by `BrokerResolver` and disabled until live sync/risk-state integration is complete. The agent can be started in live mode for testing configuration validation only:
```bash
atlas run --mode live
```

All actions will be recorded in the tamper-evident audit log (`audit/audit.log`).

