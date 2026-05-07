# Routine Trader Template

This workspace template contains the prompts, schedules, memory files, skills, and runtime directories needed for a routine-first Atlas Agent paper trader.

Start in paper mode:

```bash
atlas validate
atlas routine run pre_market --mode paper
atlas routine run market_open --mode paper
```

Live mode is disabled by default and requires explicit configuration, broker credentials, risk checks, and approval gates.

