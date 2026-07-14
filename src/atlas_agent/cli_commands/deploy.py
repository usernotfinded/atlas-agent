# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/deploy.py
# PURPOSE: CLI handler for `atlas deploy` — writes deployment templates for review.
#          Scaffolds files; deploys nothing.
# DEPS:    atlas_agent.deploy
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from atlas_agent.cli_context import CLIContext
from atlas_agent.cli_io import display_path


def handle_deploy(context: CLIContext) -> int:
    args = context.args
    if args.deploy_command in {"docker", "systemd", "vps", "serverless"}:
        return _handle_deploy(args.deploy_command)
    return 0


def _handle_deploy(kind: str) -> int:
    from atlas_agent.deploy import ensure_deploy_files

    files = ensure_deploy_files(kind)
    for generated in files:
        action = "created" if generated.created else "existing"
        print(f"{action}: {display_path(generated.path)}")
    return 0
