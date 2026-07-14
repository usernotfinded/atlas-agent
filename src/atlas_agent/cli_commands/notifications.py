# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/notifications.py
# PURPOSE: CLI handler for `atlas notifications` — inspect the delivery history.
# DEPS:    notifications.storage
# ==============================================================================

"""CLI handler for `atlas notifications`."""

# --- IMPORTS ---
from __future__ import annotations

from pathlib import Path

from atlas_agent.cli_context import CLIContext


def handle_notifications(context: CLIContext) -> int | None:
    args = context.args
    config = context.config

    if args.command == "notifications":
        from atlas_agent.notifications import (
            NotificationConfig,
            NotificationPayload,
            NotificationSeverity,
            send_notification,
            save_result,
        )

        transport_str = getattr(args, "transport", "dry_run")
        severity_str = getattr(args, "severity", "info")
        message = getattr(args, "message", "")
        title = getattr(args, "title", "")
        source = getattr(args, "source", "cli")
        dry_run = getattr(args, "dry_run", True)

        # Always default to dry_run unless explicitly slack and not --dry-run
        effective_transport = transport_str
        if dry_run and transport_str == "slack":
            effective_transport = "dry_run"

        config = NotificationConfig(
            enabled=True,
            transport=effective_transport,  # type: ignore[arg-type]
        )

        payload = NotificationPayload(
            severity=NotificationSeverity(severity_str),
            title=title,
            message=message,
            source=source,
            source_command=f"notifications {getattr(args, 'notifications_command', '')}",
            mode=config.trading_mode if hasattr(config, "trading_mode") else "unknown",
        )

        result = send_notification(payload, config)
        save_result(result, Path.cwd())

        print(f"Notification result: {result.status}")
        print(f"  Transport: {result.transport.value}")
        print(f"  Message: {result.message}")
        if result.redacted_preview:
            print(f"  Preview:\n{result.redacted_preview}")
        if result.error_code:
            print(f"  Error: {result.error_code} — {result.error_detail}")
        return 0 if result.status in ("delivered", "dry_run", "disabled") else 1
    return None

