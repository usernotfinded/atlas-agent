# Notifications

Atlas Agent includes a safe, disabled-by-default notification layer.

## Default behavior

- Notifications are **disabled by default**.
- The default transport is `disabled`.
- No network calls are made unless explicitly configured.
- No real credentials are required for tests or dry-run usage.

## Transports

### disabled

Returns a structured disabled result immediately. No network calls.

### dry_run

Returns a success-like dry-run result with a redacted payload preview. No network calls.

### slack

Sends a message to a Slack incoming webhook URL.

- Requires `SLACK_WEBHOOK_URL` environment variable or explicit `slack_webhook_url` config.
- Fails closed if the webhook URL is missing.
- Never logs or prints the webhook URL.

## CLI

```bash
# Test dry-run notification (default, safe)
atlas notifications test

# Send a dry-run notification with custom message
atlas notifications send --message "Custom message" --severity warning

# All commands default to dry-run mode
```

## Security

- Webhook URLs are treated as secrets and redacted before logging.
- Notification payloads include a disclaimer that they are not trading instructions.
- Notifications never execute trades, call providers, call brokers, activate skills, or execute learning suggestions.
- Missing configuration fails closed with a structured error result.

## Tests

All notification tests run offline without real credentials:

```bash
PYTHONPATH=src python3.11 -m pytest tests/notifications -q
```
