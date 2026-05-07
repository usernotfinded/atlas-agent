# Remote Routines

Remote routines are stateless runs against a cloned repository. Each run reads Markdown memory, uses configured environment variables, executes `atlas agent run --mode auto`, writes reports, updates memory, optionally sends ClickUp notifications, and optionally commits/pushes changes.

Do not store keys in the repo. Configure keys in the remote runtime. Start with paper mode and keep `ALLOW_GIT_PUSH=false` until reviewed.

The recommended schedule is to run the autonomous agent command every 30–60 minutes during your intended operating hours:

```bash
atlas agent run --mode auto
```

Atlas Agent will automatically detect the market state (open vs. closed) and decide whether to run a market execution cycle (which respects `TRADING_MODE` and live gates) or a safe closed-market simulation/research cycle.

You do not need to schedule `pre_market`, `market_open`, `midday_scan`, and `market_close` at fixed times unless you want strict manual control.

