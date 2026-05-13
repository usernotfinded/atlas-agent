# Live Trading

**DANGER:** Live trading involves real financial risk and can lose money. 

In Atlas Agent v0.5.5, live trading is strictly
 **disabled by default**. Enabling it requires passing through a multi-stage gate system. Live broker support is not production-grade.

## Mandatory Prerequisites
1.  **Explicit Mode**: `TRADING_MODE=live` and `ENABLE_LIVE_TRADING=true`.
2.  **Valid Broker Credentials**: Configured in `.env.atlas`.
3.  **Risk Validation**: The `RiskManager` must have a valid configuration in `.atlas/config.toml`.
4.  **Broker Sync**: `atlas broker sync` is the intended workflow for keeping local account state aligned with the broker. Live sync is currently deferred until live adapter maturity improves.
5.  **Manual Approval**: The default `ORDER_APPROVAL_MODE=manual_live` requires every order to be approved via `atlas approve-order`.
6.  **Kill-Switch Gating**: The kill switch must be in the `disabled` state.

## Live Execution Path
1.  **Agent Proposal**: The `AgentLoop` proposes an order tool call.
2.  **Risk Check**: `RiskManager` intercepts and validates against limits.
3.  **Approval Gate**: The order is placed in `pending_orders/` and an approval is requested. See [Pending Orders](pending-orders.md) for details.
4.  **Manual Review**: The operator reviews the order and approves it via CLI.
5.  **Order Placement**: Only after approval, and only once live sync/risk-state integration is implemented and `BrokerResolver` enables `can_submit`, is the order sent to the live broker adapter. Currently, live submit remains gated and disabled.
6.  **Audit**: Every step is recorded in the tamper-evident audit hash-chain.

**Responsibility:** You are solely responsible for your live trading configuration, risk limits, and financial outcomes.

