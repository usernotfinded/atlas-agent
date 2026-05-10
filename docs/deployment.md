# Deployment

Atlas Agent can run locally, on a small VPS, in Docker, under systemd, as
scheduled serverless jobs, or alongside GPU workers for local heavy models.

Deployment choice does not change the trading safety model. Broker execution
must stay behind broker adapters, deterministic risk gates, approval policy,
kill-switch checks, and audit logs.

The deployment files under `deploy/` are templates. They must not contain
secrets. Store provider keys, broker keys, Telegram tokens, and allowed Telegram
user IDs in local environment files or platform secret stores.

Generate or refresh templates:

```bash
atlas deploy docker
atlas deploy systemd
atlas deploy vps
atlas deploy serverless
```

Runtime command:

```bash
atlas run --mode paper --continuous
```

Before continuous operation:

- Run `atlas validate`.
- Confirm live trading is disabled unless explicitly intended.
- Confirm approvals, risk limits, and kill-switch behavior.
- Keep memory and reports free of credentials.
