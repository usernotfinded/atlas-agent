# ClickUp Notifications

ClickUp notifications use `CLICKUP_API_TOKEN` with either `CLICKUP_TASK_ID` for comments or `CLICKUP_LIST_ID` for task creation.

```bash
omni-trade notify clickup --file reports/daily/latest.md
```

If the token or target is missing, the CLI fails safely and does not print secrets.

