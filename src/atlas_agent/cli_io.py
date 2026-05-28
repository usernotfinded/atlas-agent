from __future__ import annotations

from pathlib import Path
from typing import Any

from atlas_agent.output import emit_json, error_envelope, success_envelope
from atlas_agent.redaction import redact_text


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
    return 2


def display_path(path: Path) -> str:
    """Return a path relative to the current working directory if possible."""
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def redact_cli_text(text: str) -> str:
    """Redact sensitive values from text using the central redaction engine."""
    return redact_text(text)
