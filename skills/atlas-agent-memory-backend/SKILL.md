# atlas-agent-memory-backend

## When to use this skill

- Changes to Markdown memory files (read, write, append, format)
- Changes to SQLite memory index, FTS search, or `memory.sqlite`
- Changes to `rebuild-index`, `memory search`, or memory ingestion
- Changes to memory snippet generation, redaction, or truncation
- Changes to memory corruption handling or recovery
- Changes to how the agent loop loads memory into context

## Files and areas this applies to

- `memory/` workspace directory (Markdown files)
- `src/atlas_agent/learning/memory_index.py`
- `src/atlas_agent/cli.py` (`memory` subcommands)
- `src/atlas_agent/redaction.py` (snippet redaction)
- Any new memory storage or search module

## Non-negotiable rules

1. **Markdown memory is the source of truth.** SQLite is an optional index/cache only. Every feature that reads memory must work when SQLite is absent.
2. **SQLite index must be rebuildable.** The `atlas memory rebuild-index` command must regenerate the index from Markdown files. Index corruption must be recoverable by rebuilding.
3. **Memory snippets must be redacted.** Snippets returned from memory search must not contain secrets, API keys, or credential-like strings.
4. **Memory writes must append history.** Do not erase previous memory entries. Append new entries and preserve historical context.
5. **Memory files must not be committed.** `memory/*.md`, `memory.sqlite`, and index files must be in `.gitignore`.
6. **Memory search must degrade gracefully.** If the SQLite index is missing, corrupted, or query fails, fall back to Markdown file scanning or return empty results with a warning.
7. **Memory context must be bounded.** When loading memory into an agent prompt, limit the total size to avoid context window overflow. Summarize or truncate rather than injecting full files.

## Required checks

- [ ] Memory read works when `memory.sqlite` is absent
- [ ] `atlas memory rebuild-index` succeeds and rebuilds the index
- [ ] Memory snippets do not contain secrets (run `scripts/check_forbidden_claims.py` or manual grep)
- [ ] Memory files are in `.gitignore`
- [ ] Memory append does not erase history

## Required tests or verification commands

```bash
python3.11 -m pytest tests/ -q -k "memory"
# Manual fallback test:
rm -f .atlas/memory.sqlite
atlas memory search AAPL
```

## Output format expected

When changing memory behavior, produce:
1. Source of truth (Markdown files and their paths)
2. Index strategy (SQLite/FTS or other) and rebuild command
3. Fallback behavior when index is missing or corrupted
4. Snippet redaction strategy
5. Context size limits for agent prompt injection

## Common failure modes to avoid

- **SQLite-only memory.** A feature that only queries `memory.sqlite` breaks when the index is missing. Always provide a Markdown fallback.
- **Overwriting memory files.** Replacing `memory/trade_journal.md` with a single new entry destroys historical context.
- **Unredacted snippets.** Memory search returning raw API keys from old logs creates a secret leak.
- **Committing memory files.** Memory contains runtime data and potentially secrets. Ensure `.gitignore` covers `memory/`.
- **Unbounded memory context.** Loading 50k tokens of memory into a prompt with a 16k context window causes truncation of the actual task.
