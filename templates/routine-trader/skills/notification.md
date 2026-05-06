# Notification Skill

Use after a routine writes a report or creates pending live orders.

Inputs: report summary, order status, pending order path, errors.

Outputs: short ClickUp comment or task update.

Safety rules: use `ClickUpNotifier`; never print `CLICKUP_API_TOKEN`; do not include secrets or raw credentials; keep notifications concise.

Failure modes: missing token, missing task/list ID, network error, ClickUp API failure.

Example: send a market-close recap with report path and pending order count.

