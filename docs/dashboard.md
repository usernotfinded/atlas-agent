# Dashboard

`atlas dashboard` renders a static local HTML dashboard at `.atlas/dashboard/index.html`.

The dashboard is local-only and read-only. It is not a trading interface, does not expose execution controls, does not call providers, does not call brokers, and is not financial advice.

## Scope

The dashboard summarizes local Atlas state only:

- system health
- safety status
- portfolio summary
- backtest summaries
- report summaries
- reflection summaries
- skill candidate and skill library summaries
- learning suggestion summaries
- audit and event summaries
- warnings
- missing data

The renderer does not invent content. Empty or absent local artifacts are shown explicitly as `No data available` or listed under missing data.

## Safety Boundaries

The dashboard has no controls to trade, submit orders, enable live trading, enable provider execution, enable broker execution, activate skills, run learning suggestions, connect brokers, connect providers, publish releases, or mutate configuration.

The generated HTML uses inline local CSS only. It does not load JavaScript frameworks, external scripts, or CDN assets.

The dashboard does not call provider APIs or broker APIs. It reads local files and config-derived status summaries collected by the dashboard data layer.

The dashboard contains no financial advice, no profit guarantees, and no claim that trading removes risk.

## CLI

```bash
atlas dashboard --json
atlas dashboard --format markdown
atlas dashboard --format html
```

`--json` and Markdown output print to stdout. HTML output writes `.atlas/dashboard/index.html`.
