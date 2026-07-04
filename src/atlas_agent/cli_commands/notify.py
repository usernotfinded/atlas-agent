"""CLI handler for `atlas notify`."""
from __future__ import annotations


from atlas_agent.cli_context import CLIContext


def handle_notify(context: CLIContext) -> int | None:
    args = context.args
    from atlas_agent.notifications.clickup import ClickUpNotifier
    from atlas_agent.notifications.clickup import NotificationConfigurationError

    if args.command == "notify" and args.notify_command == "clickup":
        if not args.file.exists():
            print(f"notification skipped safely: file not found: {args.file}")
            return 0
        try:
            ClickUpNotifier().send(args.file.read_text(encoding="utf-8")[:2000])
        except NotificationConfigurationError as exc:
            print(f"notification skipped safely: {exc}")
            return 0
        print("ClickUp notification sent")
        return 0
    return None

