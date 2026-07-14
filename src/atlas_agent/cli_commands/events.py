# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/events.py
# PURPOSE: CLI handler for `atlas events` — tails the event trail and runs the
#          doctor over it (malformed records, secrets that escaped redaction).
# DEPS:    events.log, events.doctor
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from typing import Any

from atlas_agent.cli_context import CLIContext
from atlas_agent.cli_io import emit_cli_success
from atlas_agent.events import (
    diagnose_events,
    latest_event_file,
    read_event_file,
)


def handle_events(context: CLIContext) -> int:
    args = context.args
    config = context.config

    if args.events_command == "list":
        latest = latest_event_file(config.events_dir)
        events = read_event_file(latest) if latest else []
        if len(events) > max(args.limit, 1):
            events = events[-max(args.limit, 1) :]
        if getattr(args, "json", False):
            return emit_cli_success("atlas events list", _events_to_payload(events))
        if not events:
            print(f"No event logs found under {config.events_dir}.")
            return 0
        for event in events:
            print(
                f"{event.get('timestamp')} {event.get('event_type')} "
                f"run={event.get('run_id')} mode={event.get('mode')}"
            )
        return 0

    if args.events_command == "tail":
        latest = latest_event_file(config.events_dir)
        events = read_event_file(latest) if latest else []
        if len(events) > max(args.limit, 1):
            events = events[-max(args.limit, 1) :]
        if not events:
            print(f"No event logs found under {config.events_dir}.")
            return 0
        for event in events:
            print(
                f"{event.get('timestamp')} {event.get('event_type')} "
                f"run={event.get('run_id')} mode={event.get('mode')}"
            )
        return 0

    if args.events_command == "doctor":
        report = diagnose_events(config.events_dir)
        print(f"Event Doctor: files={report.files_scanned} events={report.events_scanned}")
        for item in report.errors:
            print(
                f"[ERROR] {item.code}: {item.message} "
                f"({item.path or 'n/a'}{':' + str(item.line) if item.line else ''})"
            )
        for item in report.warnings:
            print(
                f"[WARN] {item.code}: {item.message} "
                f"({item.path or 'n/a'}{':' + str(item.line) if item.line else ''})"
            )
        return 0 if report.ok else 2

    return 0


def _events_to_payload(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(events),
        "events": events,
    }
