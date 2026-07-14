# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/research/_shared.py
# PURPOSE: Helpers common to the research subcommand handlers.
# DEPS:    cli_io
# ==============================================================================

"""Shared helpers for `atlas research` subcommands."""

# --- IMPORTS ---
from __future__ import annotations

import json


def _research_error_json(status: str, message: str) -> None:
    print(json.dumps({"ok": False, "status": status, "message": message}, indent=2, sort_keys=True))


def _research_error_text(prefix: str, message: str) -> None:
    print(f"{prefix} skipped safely: {message}")
