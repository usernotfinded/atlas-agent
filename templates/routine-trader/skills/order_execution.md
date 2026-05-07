# Order Execution Skill

Use when a validated proposed order must move through the execution path.

Inputs: approved decision, proposed order, mode, risk result, approval state.

Outputs: paper fill, live pending order, live rejection, or broker result.

Safety rules: paper orders can execute automatically; live orders become pending orders unless approved; never bypass `OrderRouter`; never call brokers directly from AI output.

Failure modes: missing approval, stale approval, risk rejection, kill switch, broker credentials missing.

Example: in live mode create `pending_orders/<order_id>.json` and wait for `atlas approve-order <order_id>`.

