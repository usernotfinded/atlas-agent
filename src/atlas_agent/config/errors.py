# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    config/errors.py
# PURPOSE: Turns raw TOML and pydantic failures into one controlled error type
#          with an operator-readable message. A bad config must fail loudly and
#          legibly — never as a pydantic traceback the user has to decode.
# DEPS:    pydantic (ValidationError)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError


# ==============================================================================
# ERROR TYPE
# ==============================================================================

class AtlasConfigError(ValueError):
    """Controlled Atlas configuration load/validation error."""


# ==============================================================================
# ERROR FORMATTING
# ==============================================================================

def format_toml_syntax_error(path: Path, exc: Exception) -> AtlasConfigError:
    line = getattr(exc, "lineno", None)
    col = getattr(exc, "colno", None)
    location = ""
    if line is not None and col is not None:
        location = f" (line {line}, column {col})"
    return AtlasConfigError(f"Invalid TOML syntax in {path}{location}.")


def format_schema_validation_error(exc: ValidationError) -> AtlasConfigError:
    entries: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", ()) if part is not None) or "<root>"
        msg = err.get("msg", "invalid value")
        entries.append(f"{loc}: {msg}")
        # Capped at 3: a single bad nested field can make pydantic emit dozens of
        # errors, and a wall of them buries the one the user actually needs to fix.
        if len(entries) >= 3:
            break
    details = "; ".join(entries) if entries else "invalid settings"
    # Only `loc` and pydantic's own `msg` are interpolated — never the offending
    # value, which may itself be the secret the config was rejected for.
    return AtlasConfigError(f"Invalid Atlas config schema: {details}")
