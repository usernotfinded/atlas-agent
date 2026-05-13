# Demo Recording Guide

This document describes how to record a short terminal demo of Atlas Agent.

## Recording script

Run the reproducible paper workflow from the repository root:

```bash
./scripts/demo_paper_workflow.sh
```

## What to expect

| Step | Expected behavior |
|---|---|
| `atlas init` | Creates a temporary routine-trader workspace. |
| `atlas discipline setup --manual --yes` | Creates the safe default discipline profile required by agentic workflows. |
| `atlas config set market.symbol ATLAS-DEMO` | Sets an explicit demo symbol without implying a product default. |
| `atlas validate` | Reports readiness while keeping the workspace read-only. |
| `atlas run --mode paper --dry-run --symbol ATLAS-DEMO` | Prints the planned paper workflow without sending live broker orders. |
| `atlas backtest run` | Runs the deterministic sample-data backtest with the `DEMO-SYMBOL` fixture. |
| `atlas audit verify --all` | Verifies any run manifests created during the session. Exit code `0` means the hash-chain is intact. |

## Recording tips

- Use a clean terminal with no unrelated files visible.
- Ensure the prompt shows the current directory clearly.
- Do not show real API keys or broker credentials.
- Keep the recording under 60 seconds.
- If you create a GIF, export it to `assets/atlas-demo.gif` only after checking every frame for secrets.

## After recording

1. Check that no secrets appear in the GIF frames.
2. Add `assets/atlas-demo.gif` to the repository only if the recording is clean and current.
3. Update README.md to render the GIF only after the file exists.
