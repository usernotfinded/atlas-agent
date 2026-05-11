# Discipline Profile

Atlas Agent uses a **discipline profile** to shape how the AI communicates and reasons. It is not a strategy file; it does not contain trading rules or signals. It describes the agent's temperament, communication style, and risk posture.

## Mandatory for agentic workflows

Atlas **requires** an explicit user discipline profile before running any agentic trading or research workflow. There is no operational default. If `.atlas/discipline.md` is missing, commands like `atlas run`, `atlas run-once`, `atlas routine run`, and `atlas scheduler run` are blocked with:

```
Atlas Discipline Profile is not configured. Run `atlas discipline setup` before starting agentic trading workflows.
```

Deterministic non-agentic backtests (e.g. `atlas backtest run`) do not require a discipline profile.

## Setup commands

```
atlas discipline show              # Show current discipline (default or user)
atlas discipline validate          # Check the user discipline for errors
atlas discipline set <text>        # Set a user discipline profile
atlas discipline generate          # Print a generation prompt for your LLM
atlas discipline reset             # Remove user discipline and revert to default
atlas discipline setup --manual   # Create from the safe built-in template
atlas discipline setup --manual --yes  # Non-interactive setup (for CI/scripts)
atlas discipline doctor            # Report discipline status
```

## Setting a custom discipline

You can set a freeform description. Atlas will sanitize it and append the required safety sentence automatically:

```
atlas discipline set "I am a long-term value investor. I prefer detailed reasoning and conservative position sizing."
```

Validation rejects phrases that attempt to override safety controls, such as "ignore risk limits" or "bypass kill switch."

## Non-interactive / CI setup

For GitHub Actions, demos, and scripted workflows, create the discipline profile before running any agentic routine:

```bash
atlas init . --template routine-trader
atlas discipline setup --manual --yes
atlas config set market.symbol DEMO-SYMBOL
atlas routine run pre_market --mode paper
```

`--yes` skips the interactive confirmation prompt and writes the safe built-in template directly. It does not require an AI provider or API keys.

## How it works

When the agent builds its system prompt, it layers:

1. The base system identity.
2. Your user discipline profile (required for agentic workflows).

The default discipline template exists only as a non-operational reference. It is never used as a runtime fallback.

## Privacy

User discipline profiles are stored in `.atlas/discipline.md` inside the workspace. This file is gitignored by default so personal preferences are not committed.
