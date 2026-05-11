# Risk Model

Atlas Agent v0.5.0 implements a multi-stage deterministic risk model.

## Core Components

### 1. Risk Exposure V2
Real-time calculation of current portfolio exposure across all positions, normalized by account equity.

### 2. Pending Orders V3
Advanced projection that calculates the "worst reasonable" outcome by aggregating current positions with all active and pending orders. This prevents "over-exposure" from multiple pending limit orders.

## Risk Limits
The `RiskManager` enforces the following hard limits:
- **Maximum Position Notional**: Absolute dollar value limit for any single symbol.
- **Maximum Single Trade Notional**: Absolute dollar value limit for any single order.
- **Daily Loss Limit**: Blocks new orders if the day's realized + unrealized PnL drops below a threshold.
- **Portfolio Exposure Pct**: Maximum percentage of total equity allowed as net exposure.
- **Symbol Allowlist/Blocklist**: Restricted trading to approved assets.
- **Minimum Confidence**: Rejects orders with an AI confidence score below the configured threshold.
- **Leverage Policy**: Leverage is disabled by default.

## Verification
Risk decisions are recorded as `risk_evaluation_allowed` or `risk_evaluation_blocked` events in the audit hash-chain. You can view your current risk status with:
```bash
atlas risk status
```

