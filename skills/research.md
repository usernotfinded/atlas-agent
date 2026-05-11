# Research Skill

Use when a routine needs market context, catalysts, news, or benchmark context.

Inputs: symbol, watchlist, open positions, strategy rules, recent reports.

Outputs: concise research summary, catalysts, uncertainty, citations when available.

Safety rules: use the configured web research provider; avoid unsupported market claims; never make profit guarantees; never print API keys; clearly label uncertainty.
Failure modes: missing research API key, stale data, no citations, provider timeout. If research fails, continue with local data and state the limitation.

Example: summarize SPY market regime, <SYMBOL> catalysts, and risk events relevant to current watchlist.

