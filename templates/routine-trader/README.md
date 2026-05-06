# OmniTradeAI Routine Trader Workspace

This workspace is generated from the `routine-trader` template. It keeps local trading memory, routine prompts, reports, pending orders, and audit logs outside the package source.

## First Run

```bash
omni-trade validate
omni-trade routine run pre_market --mode paper
omni-trade routine run market_open --mode paper
```

Copy `.env.example` to `.env` only for local development. Do not commit `.env`, API keys, broker credentials, tokens, generated pending orders, or audit logs.

## Runtime State

- `memory/`: Markdown memory read and updated by routines.
- `reports/daily/`: generated daily routine reports.
- `reports/weekly/`: generated weekly routine reports.
- `pending_orders/`: live approval files; live mode remains gated.
- `audit/`: JSONL audit logs.
- `.omni/locks/`: local routine lock files.

