from __future__ import annotations

from pathlib import Path
from typing import Any

import os

from atlas_agent.cli_context import CLIContext
from atlas_agent.cli_io import emit_cli_success
from atlas_agent.workspace import (
    WorkspaceResolution,
    clear_default_workspace,
    get_default_workspace,
    is_workspace,
    resolve_workspace,
    set_default_workspace,
)


def handle_workspace(context: CLIContext) -> int:
    args = context.args
    resolution = resolve_workspace(getattr(args, "workspace", None))

    if args.workspace_command == "show":
        default_ws = get_default_workspace()
        resolved = resolution.path
        print(f"Current directory: {Path.cwd()}")
        print(f"Resolved workspace: {resolved or 'not resolved'}")
        print(f"Resolution source: {resolution.source or 'none'}")
        print(f"Default workspace: {default_ws or 'not set'}")
        if resolution.warning:
            print(f"Warning: {resolution.warning}")
        return 0

    if args.workspace_command == "set":
        path = Path(args.path).resolve()
        if not is_workspace(path):
            print(f"Error: {path} does not look like a valid Atlas workspace.")
            return 2
        set_default_workspace(path)
        print(f"Default workspace set to: {path}")
        return 0

    if args.workspace_command == "clear":
        clear_default_workspace()
        print("Default workspace cleared.")
        return 0

    if args.workspace_command == "doctor":
        payload = _workspace_doctor_payload(resolution)
        if getattr(args, "json", False):
            return emit_cli_success("atlas workspace doctor", payload)
        print("Workspace Doctor")
        print(f"Current directory: {payload['current_directory']}")
        print(f"Resolved workspace: {payload['resolved_workspace'] or 'not resolved'}")
        print(f"Resolution source: {payload['resolution_source'] or 'none'}")
        print(f"Default workspace: {payload['default_workspace'] or 'not set'}")
        if payload["warning"]:
            print(f"Warning: {payload['warning']}")
        if payload["resolved_workspace"] and not payload["missing_paths"]:
            print("Workspace structure looks valid.")
            return 0
        if payload["missing_paths"]:
            print("Missing paths:")
            for missing in payload["missing_paths"]:
                print(f"- {missing}")
        for guidance in payload["guidance"]:
            print(guidance)
        return 2

    return 0


def _workspace_doctor_payload(resolution: WorkspaceResolution) -> dict[str, Any]:
    default_workspace = get_default_workspace()
    payload: dict[str, Any] = {
        "ok": False,
        "current_directory": str(Path.cwd()),
        "resolved_workspace": str(resolution.path) if resolution.path else None,
        "resolution_source": resolution.source,
        "default_workspace": str(default_workspace) if default_workspace else None,
        "environment_workspace": os.getenv("ATLAS_WORKSPACE"),
        "warning": resolution.warning,
        "missing_paths": [],
        "guidance": [],
    }
    if resolution.path is None:
        payload["guidance"] = [
            "Create a workspace: atlas init my-trader --template routine-trader --set-default",
            "or set one: atlas workspace set <path>",
        ]
        return payload

    expected = (
        "memory",
        "routines",
        "skills",
        "reports",
        "pending_orders",
        "audit",
        "events",
        "configs",
    )
    missing = [
        name for name in expected if not (resolution.path / name).exists()
    ]
    payload["missing_paths"] = missing
    payload["ok"] = not missing
    return payload
