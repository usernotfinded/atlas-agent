# Live Trading

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

**DANGER:** Live trading involves real financial risk and can lose money.

In Atlas Agent v0.6.9, live trading is strictly **disabled by default**. Enabling it requires passing through a multi-stage gate system. Live broker support is not production-grade.

## Mandatory Prerequisites
1.  **Explicit Mode**: `TRADING_MODE=live` and `ENABLE_LIVE_TRADING=true`.
2.  **Valid Broker Credentials**: Configured in `.env.atlas`.
3.  **Risk Validation**: The `RiskManager` must have a valid configuration in `.atlas/config.toml`.
4.  **Broker Sync**: `atlas broker sync` supports Alpaca read-only live sync for account state, positions, open orders, and balances. Binance, CCXT, and IBKR sync remain deferred.
5.  **Manual Approval**: The default `ORDER_APPROVAL_MODE=manual_live` requires every order to be approved via `atlas approve-order`. Note: in live **analysis-only** mode, the agent consumes live broker snapshots but proposed orders return `live_analysis_only` and do **not** create pending order files.
6.  **Kill-Switch Gating**: The kill switch must be in the `disabled` state.

## Live Analysis-Only Mode
When `mode=live` (or `auto` resolves to live with `ENABLE_LIVE_TRADING=true`):
1.  **Broker Sync**: The runner synchronizes account, positions, and open orders from Alpaca into a `PortfolioSnapshot`.
2.  **Agent Analysis**: The `AgentLoop` receives the live portfolio snapshot and can analyze real positions and exposure.
3.  **Order Proposal**: If the agent proposes an order, `RiskManager` validates it against limits.
4.  **Deferred Execution**: If risk passes, the tool returns `live_analysis_only`. The order is **not** written to `pending_orders/`, **not** sent to the approval manager, and **not** submitted to the broker.

## Live Execution Path (Deferred)
1.  **Agent Proposal**: The `AgentLoop` proposes an order tool call.
2.  **Risk Check**: `RiskManager` intercepts and validates against limits.
3.  **Approval Gate**: For legacy/manual live paths, the order may be placed in `pending_orders/` and an approval requested. See [Pending Orders](pending-orders.md) for details.
4.  **Manual Review**: The operator reviews the order and approves it via CLI.
5.  **Order Placement**: Only after approval, and only once `BrokerResolver` enables `can_submit` and `resolve_execution_broker("live")` returns a broker, is the order sent to the live broker adapter. Currently, `can_submit=false` for all live brokers and live submit remains gated and disabled.
6.  **Audit**: Every step is recorded in the tamper-evident audit hash-chain.

**Responsibility:** You are solely responsible for your live trading configuration, risk limits, and financial outcomes.
