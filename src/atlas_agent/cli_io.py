# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_io.py
# PURPOSE: The single exit path for CLI command handlers. Pairs each envelope with
#          its exit code so that "what the machine reads" and "what the shell sees"
#          can never disagree.
# DEPS:    atlas_agent.output (envelopes), atlas_agent.redaction (scrubbing)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from pathlib import Path
from typing import Any

from atlas_agent.output import emit_json, error_envelope, success_envelope
from atlas_agent.redaction import redact_text


# ==============================================================================
# COMMAND RESULT EMISSION
# ==============================================================================
#
# Handlers `return emit_cli_*(...)` rather than emitting and returning separately.
# Binding the envelope and the exit code in one call is what stops a handler from
# printing an error envelope and then falling through to exit 0.

def emit_cli_success(command: str, data: dict[str, Any]) -> int:
    """Emit a JSON success envelope and return exit code 0."""
    emit_json(success_envelope(command, data))
    return 0


def emit_cli_error(
    command: str,
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> int:
    """Emit a JSON error envelope and return exit code 2."""
    emit_json(error_envelope(command, code=code, message=message, details=details))
    # 2, not 1: exit 1 is what an uncaught Python traceback produces. Reserving a
    # distinct code lets callers and CI tell "the command ran and said no" apart
    # from "the command crashed".
    return 2


# ==============================================================================
# DISPLAY HELPERS
# ==============================================================================

def display_path(path: Path) -> str:
    """Return a path relative to the current working directory if possible."""
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        # Path is outside the cwd (a different volume, or an absolute workspace).
        # Falling back to the absolute form beats emitting a pile of `../../..`.
        return str(path)


def redact_cli_text(text: str) -> str:
    """Redact sensitive values from text using the central redaction engine."""
    return redact_text(text)
