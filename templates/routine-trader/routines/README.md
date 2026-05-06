# Routine Trader Template

This workspace template contains the prompts, schedules, memory files, skills, and runtime directories needed for a routine-first OmniTradeAI paper trader.

Start in paper mode:

```bash
omni-trade validate
omni-trade routine run pre_market --mode paper
omni-trade routine run market_open --mode paper
```

Live mode is disabled by default and requires explicit configuration, broker credentials, risk checks, and approval gates.

