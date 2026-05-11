# Discipline Profile

Atlas Agent uses a **discipline profile** to shape how the AI communicates and reasons. It is not a strategy file; it does not contain trading rules or signals. It describes the agent's temperament, communication style, and risk posture.

## Default discipline

Every workspace uses the built-in default discipline unless a user profile is configured. The default is:

- **Decision temperament:** Cautious and evidence-seeking.
- **Reasoning style:** Step-by-step and transparent.
- **Communication style:** Concise, structured, and respectful.
- **Risk posture:** Conservative.
- **Uncertainty handling:** Explicitly state confidence levels and missing information.
- **No-trade bias:** Default to no action unless the case is compelling.
- **Forbidden overrides:** User discipline cannot override Atlas risk gates, approval queues, kill switch, audit logging, broker sync checks, reference price requirements, or live-trading safeguards.

## Commands

```
atlas discipline show       # Show current discipline (default or user)
atlas discipline validate   # Check the user discipline for errors
atlas discipline set <text> # Set a user discipline profile
atlas discipline generate  # Print a generation prompt for your LLM
atlas discipline reset     # Remove user discipline and revert to default
```

## Setting a custom discipline

You can set a freeform description. Atlas will sanitize it and append the required safety sentence automatically:

```
atlas discipline set "I am a long-term value investor. I prefer detailed reasoning and conservative position sizing."
```

Validation rejects phrases that attempt to override safety controls, such as "ignore risk limits" or "bypass kill switch."

## How it works

When the agent builds its system prompt, it layers:

1. The base system identity.
2. The default discipline profile.
3. Your user discipline profile (if present).

The user layer can refine tone and reasoning preferences, but it cannot remove or weaken the base safety constraints.

## Privacy

User discipline profiles are stored in `.atlas/discipline.md` inside the workspace. This file is gitignored by default so personal preferences are not committed.
