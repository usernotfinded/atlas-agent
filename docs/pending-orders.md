# Pending Orders

`pending_orders/` is the local approval queue used by Atlas Agent for paper and legacy live trading workflows.

Atlas Agent does not directly place live broker orders by default. In **paper** mode and certain **legacy/manual live** paths, proposed orders may be written to disk as pending approval records. A human must explicitly review and approve them before execution can continue.

In **live analysis-only** mode, the agent consumes live broker snapshots but proposed orders return `live_analysis_only`. They are **not** written to `pending_orders/`, **not** sent to the approval manager, and **not** submitted to the broker. Approved-order broker submission remains deferred.

## How it works

1. **Order proposal**
   The agent generates a trade recommendation.

2. **Risk and safety checks**
   The proposed order passes through the RiskManager, live-trading gates, kill-switch checks, and approval policy.

3. **Pending approval record**
   If the order is allowed but requires human approval (paper or legacy live paths), Atlas writes a JSON record under:

   ```text
   pending_orders/<order_id>.json
   ```

   Live analysis-only orders do **not** create pending approval records.

4. **Human approval**
   The order remains paused until a user explicitly approves it through the CLI.

5. **Cleanup**
   Once approved, rejected, expired, or cancelled, the pending order record is removed or archived according to the configured workflow.

## CLI usage

Check the current CLI help before use:

```bash
atlas --help
```

If enabled in the current CLI, pending orders can be approved with:

```bash
atlas approve-order <order_id>
```

## Configuration

The pending orders directory is a non-secret runtime path. It should be configured through Atlas configuration, not through secrets.

Preferred location:

```toml
[pending_orders]
dir = "pending_orders"
```

or the equivalent supported Atlas config key.

Secrets belong in:
`.env.atlas`

Non-secret local configuration belongs in:
`.atlas/config.toml`

## Safety model

Pending orders are a live-trading approval gate. They are designed to prevent live broker orders without explicit human approval.

This mechanism does not eliminate live trading risk. Users remain responsible for:
- reviewing proposed orders
- approving or rejecting trades
- broker configuration
- live-trading enablement
- risk limits
- market and execution risk

## Git hygiene

Pending order JSON files must not be committed.

The repository should keep the directory structure with a placeholder such as:
`pending_orders/.gitkeep`

but ignore runtime order records:
`pending_orders/*.json`

Pending order files may contain sensitive trading intent, including symbols, size, direction, prices, timestamps, and strategy context.
