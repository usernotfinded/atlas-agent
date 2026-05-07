# Environment Variables

Remote routine systems should inject these environment variables directly. Do not require a `.env` file in Claude Code, Codex, GitHub Actions, cron, or other remote routine environments. Never print secrets.

```bash
# Trading mode
TRADING_MODE=paper
ENABLE_LIVE_TRADING=false
LIVE_BROKER=alpaca
ORDER_APPROVAL_MODE=manual_live
KILL_SWITCH_ENABLED=false

# Alpaca
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# Research
PERPLEXITY_API_KEY=
PERPLEXITY_MODEL=sonar-pro

# ClickUp notifications
CLICKUP_API_TOKEN=
CLICKUP_WORKSPACE_ID=
CLICKUP_LIST_ID=
CLICKUP_TASK_ID=

# Git sync for remote routines
ALLOW_GIT_COMMIT=true
ALLOW_GIT_PUSH=false
GIT_COMMIT_AUTHOR_NAME=Atlas Agent
GIT_COMMIT_AUTHOR_EMAIL=atlas-agent@example.local

# Provider adapter
AI_PROVIDER=null
OPENAI_COMPATIBLE_BASE_URL=
OPENAI_COMPATIBLE_API_KEY=
OPENAI_COMPATIBLE_MODEL=
ANTHROPIC_API_KEY=
DEEPSEEK_API_KEY=
KIMI_API_KEY=
GROK_API_KEY=
OPENROUTER_API_KEY=
LOCAL_COMMAND=
```

Paper mode should be used first. Live mode requires explicit gates, broker credentials, risk controls, approval, and human responsibility for account and regulatory obligations.

