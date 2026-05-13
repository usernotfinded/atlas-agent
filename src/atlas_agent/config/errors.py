from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError


class AtlasConfigError(ValueError):
    """Controlled Atlas configuration load/validation error."""


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
        if len(entries) >= 3:
            break
    details = "; ".join(entries) if entries else "invalid settings"
    return AtlasConfigError(f"Invalid Atlas config schema: {details}")
