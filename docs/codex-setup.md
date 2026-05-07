# Codex Setup

Codex-compatible scheduled runs can use the same prompts in `routines/prompts/`. Codex should use `atlas` CLI, Markdown memory, provider adapters, broker adapters, RiskManager, and OrderRouter rather than hidden behavior.

Use `LocalCommandProvider` for Codex CLI, Claude Code, custom scripts, local model wrappers, or other command-based agents. Keep live execution behind approval and never write secrets into files.

Simulation test:

```bash
atlas agent run --mode paper
# or
atlas agent run --mode auto
```
