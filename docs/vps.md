# VPS Deployment

Atlas Agent is designed for lightweight VPS deployments depending on provider,
workload, and model choices.

Use a VPS for continuous agent operation, Telegram control, scheduled learning,
and broker-adapter access. Keep secrets outside git and validate the workspace
before enabling continuous operation.

Suggested flow:

```bash
git clone https://github.com/usernotfinded/atlas-agent.git
cd atlas-agent
python -m pip install -e . --no-build-isolation
atlas validate
atlas deploy systemd
```

Practical VPS notes:

- Keep API keys and Telegram tokens in an env file outside the repo or in the
  host secret manager.
- Run the agent under a dedicated user.
- Use systemd restart limits and logs for routine supervision.
- Keep live mode disabled unless config, credentials, risk checks, approvals,
  kill switch, and broker gates are all ready.
