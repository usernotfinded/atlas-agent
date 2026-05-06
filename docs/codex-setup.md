# Codex Setup

Codex-compatible scheduled runs can use the same prompts in `routines/prompts/`. Codex should use `omni-trade` CLI, Markdown memory, provider adapters, broker adapters, RiskManager, and OrderRouter rather than hidden behavior.

Use `LocalCommandProvider` for Codex CLI, Claude Code, custom scripts, local model wrappers, or other command-based agents. Keep live execution behind approval and never write secrets into files.

Paper-first test:

```bash
omni-trade routine run pre_market --mode paper
```

