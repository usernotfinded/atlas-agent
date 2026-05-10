# Live Alpaca Demo

**DANGER:** Live trading involves real financial risk. This demo is for educational purposes only.

## Safety Model
Live mode in Atlas Agent v0.4.0 is never enabled by default.
 It requires:
1.  **Explicit Configuration**: `TRADING_MODE=live` and `ENABLE_LIVE_TRADING=true`.
2.  **Manual Approval**: By default, every order requires manual approval via `atlas approve-order`.
3.  **Broker Sync**: Ensure your local portfolio state is synchronized with `atlas broker sync`.

## Setup
Configure your credentials in `.env.atlas`:
```bash
APCA_API_KEY_ID=YOUR_ALPACA_KEY
APCA_API_SECRET_KEY=YOUR_ALPACA_SECRET
APCA_API_BASE_URL=https://api.alpaca.markets
```

## Running
Start the agent in live mode:
```bash
atlas run --mode live
```

All actions will be recorded in the tamper-evident audit log (`audit/audit.log`).

