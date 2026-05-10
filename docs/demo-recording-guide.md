# Demo Recording Guide

This document describes the script for recording a short terminal demo of Atlas Agent.

## Recording script

Run the following commands in a clean terminal window:

```bash
# 1. Install Atlas Agent
pip install -e .

# 2. Create a workspace
atlas init demo-workspace --template routine-trader

# 3. Enter the workspace
cd demo-workspace

# 4. Validate configuration
atlas validate

# 5. Run a paper cycle
atlas run --mode paper

# 6. Verify the audit trail
atlas audit verify --all
```

## What to expect

| Step | Expected behavior |
|---|---|
| `atlas init` | Creates `demo-workspace` with a routine-trader template. |
| `atlas validate` | Confirms the workspace is configured and live trading is disabled. |
| `atlas run --mode paper` | Runs a paper cycle without sending live broker orders. If no AI provider is configured, the built-in `NullProvider` returns a deterministic hold response. |
| `atlas audit verify --all` | Verifies any run manifests created during the session. Exit code `0` means the hash-chain is intact. |

## Recording tips

- Use a clean terminal with no unrelated files visible.
- Ensure the prompt shows the current directory clearly.
- Do not show real API keys or broker credentials.
- Keep the recording under 60 seconds.
- Export the final GIF to `assets/atlas-demo.gif`.

## After recording

1. Check that no secrets appear in the GIF frames.
2. Add `assets/atlas-demo.gif` to the repository.
3. Remove the HTML comment in README.md (`<!-- demo gif placeholder -->`) and ensure the GIF renders.
