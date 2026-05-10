# Environment Variables

Atlas Agent v0.4.0 uses a dual-layer configuration system:
- **`.atlas/config.json`**: Stores non-secret workspace configuration (default symbol, risk limits, etc.).
- **`.env.atlas`**: Stores sensitive API keys and broker credentials. This file is **gitignored** and protected during updates.

Remote systems (CI/CD, Serverless) should inject these environment variables directly. **Never print secrets in logs.**

## Common Variables

```bash
# Trading and Safety
TRADING_MODE=paper                # backtest|paper|live
ENABLE_LIVE_TRADING=false         # must be true for live
LIVE_BROKER=none                  # alpaca|binance|ccxt
ORDER_APPROVAL_MODE=manual_live   # auto_paper|manual_live|disabled_live
KILL_SWITCH_ENABLED=false         # global emergency stop

# Provider and Model
AI_PROVIDER=openai_compatible     # anthropic|openai|openai_compatible|local
OPENAI_COMPATIBLE_API_KEY=YOUR_API_KEY_HERE
OPENAI_COMPATIBLE_BASE_URL=https://api.example.com/v1
OPENAI_COMPATIBLE_MODEL=gpt-4o
ANTHROPIC_API_KEY=YOUR_ANTHROPIC_KEY
DEEPSEEK_API_KEY=YOUR_DEEPSEEK_KEY
KIMI_API_KEY=YOUR_KIMI_KEY
GROK_API_KEY=YOUR_GROK_KEY
OPENROUTER_API_KEY=YOUR_OPENROUTER_KEY
LOCAL_COMMAND=

# Broker Credentials (Alpaca Example)
APCA_API_KEY_ID=YOUR_ALPACA_KEY
APCA_API_SECRET_KEY=YOUR_ALPACA_SECRET
APCA_API_BASE_URL=https://paper-api.alpaca.markets

# Research (Optional)
ATLAS_RESEARCH_API_KEY=YOUR_RESEARCH_KEY
RESEARCH_MODEL=sonar-pro

# Dead-Man Heartbeat
DEADMAN_TIMEOUT_MINUTES=15
DEADMAN_ACTION=soft_pause

# Git Sync
ALLOW_GIT_COMMIT=false
ALLOW_GIT_PUSH=false
GIT_COMMIT_AUTHOR_NAME=Atlas Agent
GIT_COMMIT_AUTHOR_EMAIL=atlas-agent@example.local

# ClickUp Notifications (Optional)
CLICKUP_API_TOKEN=YOUR_CLICKUP_TOKEN
CLICKUP_WORKSPACE_ID=YOUR_WORKSPACE_ID
CLICKUP_LIST_ID=YOUR_LIST_ID
CLICKUP_TASK_ID=YOUR_TASK_ID
```

Paper mode is the default and safest way to run. Live mode requires explicit configuration and multiple safety gates.

