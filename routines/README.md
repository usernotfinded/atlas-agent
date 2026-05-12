# Atlas Agent Routines

In Atlas Agent v0.5.3, "routines" represent
 the high-level autonomous reasoning cycles coordinated by the **AgentLoop**. The agent uses a tool-driven approach to research markets, manage memory, and execute trades.

## Execution
Run a manual autonomous cycle:
```bash
atlas run --mode paper --once
```

## Features
- **Tool-Driven Reasoning**: The agent uses 49+ builtin tools to interact with the system.
- **Memory Persistence**: Every run reads and updates Markdown journals in the `memory/` directory.
- **Auditability**: Every tool call and risk decision is recorded in the tamper-evident audit log.
- **Notifications**: Optional integration with ClickUp for remote session reports.
- **Git Sync**: Optional guarded commit/push of memory and reports.

