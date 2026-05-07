# Atlas Agent Routines

Routines are stateless scheduled runs. Each run reads Markdown memory, performs research, uses the CLI-backed trading path, writes reports, updates memory, optionally sends ClickUp notifications, and optionally commits/pushes changes.

Manual run:

```bash
atlas agent run --mode auto
```

Remote AI agents can paste prompts from `routines/prompts/`.

