# Broker Safety

## Live Order Timeouts and Reconciliation

A live order timeout/transport error must be treated as unknown execution state. The operator must reconcile by `client_order_id` before retrying. The system must not auto-resubmit.

### Expected Behavior

When a live order submission encounters a timeout or transport-level error:

1. **The order may or may not have been received by the broker.** The system cannot determine execution state from a transport failure alone.
2. **The system raises a `BrokerOperationError`** with a message indicating unknown execution state and requiring reconciliation.
3. **No automatic retry is attempted.** Re-submitting an order without confirming the prior attempt's state risks duplicate execution.

### Reconciliation Requirements

Before retrying any order that failed with a timeout or transport error:

- The operator **must** query the broker for the original `client_order_id` to determine whether the order was received, partially filled, or fully filled.
- The `AlpacaBrokerAdapter.get_order_by_client_order_id()` method is provided for this purpose.
- If the order was **not found** (404), it is safe to resubmit with a **new** `client_order_id`.
- If the order was **found**, the operator must assess its status before deciding next steps.

### Design Rationale

- **No idempotent auto-retry**: Alpaca does not guarantee idempotent order submission by `client_order_id`. Resubmitting with the same ID may be rejected or may create a duplicate depending on timing.
- **Fail-closed**: On ambiguity, the system halts and surfaces the error to the operator rather than risking unintended position changes.
- **Audit trail**: All timeout errors are logged through the standard audit pipeline, preserving the `client_order_id` for post-incident review.

### Operator Responsibility

The operator is responsible for:
- Monitoring order submission results
- Reconciling ambiguous states before retry
- Ensuring the kill switch is available for emergency halt
