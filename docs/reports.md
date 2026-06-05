# Atlas Agent Reports

Atlas Agent includes a local report generator that produces daily, weekly, and ad-hoc reports from **local data only**.

## Scope

- Reports use only files already present in the workspace (`.atlas/`, `memory/`, `events/`).
- Reports do **not** call provider APIs.
- Reports do **not** call broker APIs.
- Reports do **not** use the network.
- Reports do **not** contain fake, placeholder, or invented data.
- Reports are deterministic and safe to run offline.

## Report Types

```bash
# Daily report (Markdown)
atlas report generate --type daily --format markdown

# Weekly report (Markdown)
atlas report generate --type weekly --format markdown

# Ad-hoc report (JSON)
atlas report generate --type ad-hoc --format json

# Write to file instead of stdout
atlas report generate --type daily --format markdown --output artifacts/reports/daily.md
```

## Legacy Backtest Report

You can still generate a backtest-specific report by run ID:

```bash
atlas report generate --run-id <RUN_ID> --format markdown
```

## Report Sections

Each report includes the following sections when data is available:

- **Metadata** — report type, generation timestamp, workspace path
- **Portfolio Summary** — cash, equity, positions (from `memory/portfolio.md`)
- **Backtest Summary** — recent run count, latest run metrics (from `.atlas/backtests/`)
- **Research Summary** — artifact counts (from `.atlas/research/`)
- **Risk Summary** — configuration values (from `.atlas/config.toml`)
- **Audit / Decision Summary** — recent event counts (from `.atlas/logs/`)
- **System Health Summary** — workspace readiness and diagnostics
- **Missing Data** — explicitly lists any unavailable data sources
- **Safety Disclaimer** — research-only, not investment advice

If a section's source data is missing, the report states:

```text
No <section> data available.
```

## Output Files

Reports default to `reports/` when using the `daily`/`weekly` shorthand commands.
The `generate` command defaults to `stdout`.

Generated report files are local artifacts and must not be staged.

## Safety

- Reports remain local, offline, and research-only.
- No financial advice is given.
- No profit or performance guarantees are made.
- No secrets are printed.
