# atlas-agent-performance

## When to use this skill

- Adding caching layers (JSONL tail reading, CSV market data, tool schema cache)
- Introducing SQLite or FTS indexes for memory search
- Replacing reflection or dynamic lookups with static structures
- Optimizing hot paths in the agent loop, broker sync, or risk evaluation
- Adding benchmark scripts or performance regression tests
- Claims about throughput, latency, or resource usage in docs or PRs

## Files and areas this applies to

- `src/atlas_agent/market_data/` (CSV provider, cache invalidation)
- `src/atlas_agent/events/log.py` (JSONL tail reading)
- `src/atlas_agent/learning/memory_index.py` (SQLite/FTS index)
- `src/atlas_agent/tooling/` (schema cache)
- `src/atlas_agent/replay.py` (replay performance)
- Any new cache or index module

## Non-negotiable rules

1. **Do not claim performance improvements without benchmarks.** Every performance claim must have a reproducible benchmark artifact (script, test, or measurement log).
2. **Caches must have invalidation logic.** CSV market data must use mtime-based invalidation. SQLite memory index must have a `rebuild-index` command. Schema caches must invalidate when source files change.
3. **Optional indexes must degrade gracefully.** If SQLite is unavailable or corrupted, memory search must fall back to Markdown file scanning. Do not crash when the optional index is missing.
4. **Avoid reflection in hot paths.** Use precomputed lookup tables, cached schemas, or static dispatch instead of runtime introspection in loops.
5. **JSONL tail reading must not load full files.** `read_recent_events()` and similar functions should read from the end of the file, not parse the entire JSONL.
6. **Benchmarks must measure end-to-end behavior.** Micro-benchmarks of isolated functions are fine, but the critical metric is agent-loop or backtest wall-clock time with realistic data.
7. **Performance changes must not weaken safety.** Never skip audit writes, risk checks, or redaction for speed.

## Required checks

- [ ] New cache has explicit invalidation strategy
- [ ] Optional index has fallback behavior when absent or corrupted
- [ ] No reflection in agent-loop or broker-sync hot paths
- [ ] Benchmark artifact exists for claimed improvements
- [ ] Safety checks (audit, risk, redaction) still run in optimized paths

## Required tests or verification commands

```bash
python3.11 -m pytest tests/ -q -k "perf or cache or benchmark"
# If benchmark scripts exist:
python3.11 scripts/benchmark_<name>.py
```

## Output format expected

When making a performance change, produce:
1. The hot path being optimized
2. The caching/indexing strategy and invalidation mechanism
3. Fallback behavior for cache misses or corruption
4. Benchmark results (before and after, with data size and hardware context)
5. Confirmation that safety checks are not skipped

## Common failure modes to avoid

- **Cache without invalidation.** A CSV cache that never invalidates serves stale data after file updates.
- **Optional index treated as required.** If SQLite FTS is the only search path, the system breaks when the index is missing.
- **Reflection in loops.** Calling `getattr()`, `inspect.signature()`, or `jsonschema.validate()` inside tight loops causes unexpected slowdowns.
- **Benchmarking with unrealistic data.** A 10-row CSV benchmark does not predict behavior on 100k rows.
- **Skipping redaction for speed.** Redaction is not optional. If it is a bottleneck, optimize the redaction engine, do not bypass it.
