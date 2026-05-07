# Atlas Agent Model Roster

Atlas Agent can maintain a ranked roster of financial LLMs using the Vals AI Finance Agent benchmark. The benchmark ranking is treated as an input, not as a guarantee of trading performance. Atlas Agent filters the roster through the providers and API keys configured by the user.

```bash
atlas models update --source vals-finance-agent
atlas models list
atlas models select --top 7
atlas models doctor
```

The updater writes `configs/model_roster.yaml` and caches the last usable roster at `.atlas/cache/model_roster.json`. Tests do not require live web access. If the benchmark fetch fails, the page structure changes, or parsing returns no entries, Atlas Agent falls back to the cache and then to built-in public fallback entries.

`configs/model_sources.yaml` maps leaderboard display names to provider adapter names, required environment variable names, and provider model IDs. These model IDs are user-editable placeholders unless you have verified them with the provider or OpenAI-compatible gateway.

`--models auto` assigns these committee roles:

- Lead Financial Analyst
- Fundamental Analyst
- Market Research Analyst
- Technical Analyst
- Risk Challenger
- Execution Planner
- Final Arbiter

If fewer than seven usable models are configured, Atlas Agent reuses available models across roles or records disabled placeholders. Missing API keys are reported only by environment variable name; secret values are never printed.

The AI committee is advisory. It cannot call broker adapters directly. Orders still route through `RiskManager`, approval gates, the kill switch, audit logging, and broker adapters.
