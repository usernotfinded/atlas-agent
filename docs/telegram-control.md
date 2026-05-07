# Telegram Control Plane

Telegram is an optional remote control plane for Atlas Agent. It is intended for
status checks, controlled agent actions, pending-order review, memory lookup, and
kill-switch operations while the agent runs on a cloud VM or another remote host.

Use Telegram for operator control, not for direct broker access. Every live order
must still pass broker adapters, `RiskManager`, approval policy, kill-switch
checks, broker-specific gates, and audit logging.

Supported command surface:

- `/status`
- `/plan`
- `/run`
- `/learn`
- `/reflect`
- `/positions`
- `/pending`
- `/approve <order_id>`
- `/reject <order_id>`
- `/kill`
- `/resume`
- `/memory <query>`
- `/skills`

Required safety properties:

- Authorize Telegram user IDs through `TELEGRAM_ALLOWED_USER_IDS`.
- Store bot tokens, broker keys, and provider keys in local env files or platform
  secret stores.
- Never print or send bot tokens, broker keys, or provider keys.
- Treat Telegram as control input, not as a bypass around execution policy.

Run a local no-network diagnostic:

```bash
atlas telegram test
```
