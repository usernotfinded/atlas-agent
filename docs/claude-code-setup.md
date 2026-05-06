# Claude Code Setup

Use `routines/prompts/*.md` as copy-paste prompts for Claude Code routines. The remote routine environment should clone the GitHub repository, install OmniTradeAI, inject environment variables, run the requested prompt, and commit memory/report changes if `ALLOW_GIT_COMMIT=true`.

Do not rely on `.env` in the remote environment. Configure `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `PERPLEXITY_API_KEY`, `CLICKUP_API_TOKEN`, and provider keys through the routine environment.

Unrestricted push is optional and risky. Keep `ALLOW_GIT_PUSH=false` until paper routines are stable and repository permissions are reviewed.

Test paper mode first:

```bash
omni-trade routine run pre_market --mode paper
omni-trade routine run market_open --mode paper
omni-trade routine run market_close --mode paper
```

