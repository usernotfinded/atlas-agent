# Kill Switch Runbook

Atlas Agent supports hierarchical kill-switch modes, plus a dead-man heartbeat switch for automatic protection.

## Modes

- `soft_pause`: Blocks new orders. Existing positions remain open.
- `cancel_all`: `soft_pause` + cancels working/pending simulated/broker orders.
- `flatten_all`: `cancel_all` + attempts to close all open positions safely.
- `locked_down`: Final state after a flatten; requires operator intervention to reset.

## CLI Commands

### Status and Planning
View current status and dead-man heartbeat health:
```bash
atlas kill status
```

Generate a safety action plan (e.g., to see what "flatten" would do):
```bash
atlas kill plan --mode flatten-all
atlas kill plan --mode flatten-all --json
```

### Execution
Execute a previously generated safety plan:
```bash
atlas kill execute-plan --plan emergency_plan.json --approved
atlas kill execute-plan --plan emergency_plan.json --paper # Simulation
```

Manual triggers:
```bash
atlas kill soft-pause
atlas kill cancel-all
atlas kill flatten-all
```

Reset/Disable:
```bash
atlas kill reset
```

Manual heartbeat:
```bash
atlas kill heartbeat
```

## Dead Man's Switch (Heartbeat)

Environment variables (typically in `.env.atlas`):

```bash
DEADMAN_TIMEOUT_MINUTES=15          # 0 disables deadman
DEADMAN_ACTION=soft_pause           # soft_pause|cancel_all|flatten_all
DEADMAN_AUTO_RESET=true             # reset timer on user interaction
```

The system "fails closed": if the heartbeat is not updated within the timeout, the configured safety action is automatically triggered.

## Operational Drill (Recommended)

Run this on paper mode before any live rollout:

1. Start with no kill switch active.
2. Trigger `soft-pause` and verify new orders are rejected in `atlas audit`.
3. Escalate to `cancel-all` and verify working-order cancellation path executes.
4. Run `atlas kill plan --mode flatten-all` and inspect the generated JSON.
5. Execute the plan and verify open positions close in the paper broker.
6. Reset the kill switch with `atlas kill reset`.

## Telegram Control Surface

Current command surface (wired through control-plane helpers/CLI integration):

- `/kill`
- `/kill flatten`
- `/resume <totp>`
- `/heartbeat`

## Dead Man's Switch

Environment variables:

```bash
DEADMAN_TIMEOUT_MINUTES=15          # 0 disables deadman
DEADMAN_ACTION=soft                 # soft|cancel|flatten
DEADMAN_AUTO_RESET=true             # reset timer on user interaction
DEADMAN_ACTIVE_OUTSIDE_MARKET=false # if false, only active in market open state
DEADMAN_CHECK_INTERVAL_SECONDS=5
DEADMAN_FLATTEN_STRATEGY=market     # market|aggressive_limit
DEADMAN_FLATTEN_BPS=25
```

Heartbeat sources:

- explicit CLI heartbeat command
- Telegram `/heartbeat`
- auto-reset from user interactions when `DEADMAN_AUTO_RESET=true`

If timeout expires in active window, deadman enables kill switch using configured action and emits notifications through configured gateways.

## Operational Drill (Recommended)

Run this on paper mode before any live rollout:

1. Start with no kill switch active.
2. Trigger `soft` and verify new orders are rejected.
3. Escalate to `cancel` and verify working-order cancellation path executes.
4. Escalate to `flatten` and verify open positions close (or partial-success report is produced).
5. Attempt disable without TOTP after flatten and confirm refusal.
6. Disable with valid TOTP and verify status returns disabled.
7. Simulate deadman timeout and verify configured action triggers automatically.

## Recovery After Accidental Flatten

1. Keep kill switch enabled while assessing exposure.
2. Verify all broker-side fills/cancels and compare with Atlas audit/events.
3. Reconcile portfolio state and journal.
4. Disable kill switch only after explicit operator review (and TOTP when required).
5. Resume with paper mode first, then re-enable live mode only after safety checks.

## Notes

- Kill-switch transitions are idempotent.
- Repeated `flatten` requests do not intentionally duplicate close actions once flat.
- Legacy `memory/kill_switch.enabled` is still respected for backward compatibility.
