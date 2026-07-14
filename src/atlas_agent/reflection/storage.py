# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    reflection/storage.py
# PURPOSE: Persists reflection artifacts as browsable JSON files.
# DEPS:    reflection.models
# ==============================================================================

"""Local storage for reflection artifacts.

Stores artifacts under `.atlas/reflections/` as JSON files.
All operations are local and safe.
"""

# --- IMPORTS ---
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from atlas_agent.reflection.models import ReflectionArtifact, ReflectionStatus


REFLECTIONS_DIR = ".atlas/reflections"


def _reflections_path(workspace: str | Path = ".") -> Path:
    return Path(workspace) / REFLECTIONS_DIR


def save_artifact(
    artifact: ReflectionArtifact,
    workspace: str | Path = ".",
) -> Path:
    """Persist a reflection artifact to local storage."""
    reflections_dir = _reflections_path(workspace)
    reflections_dir.mkdir(parents=True, exist_ok=True)
    path = reflections_dir / f"{artifact.reflection_id}.json"
    import json as _json
    path.write_text(
        _json.dumps(artifact.model_dump(mode="json"), indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path


def load_artifact(
    reflection_id: str,
    workspace: str | Path = ".",
) -> ReflectionArtifact:
    """Load a reflection artifact by ID."""
    path = _reflections_path(workspace) / f"{reflection_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Reflection not found: {reflection_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return ReflectionArtifact.model_validate(data)


def list_artifacts(
    workspace: str | Path = ".",
    status: ReflectionStatus | None = None,
) -> list[dict[str, Any]]:
    """List reflection artifacts, optionally filtered by status.

    Returns metadata dicts sorted newest-first.
    """
    reflections_dir = _reflections_path(workspace)
    if not reflections_dir.exists():
        return []

    results: list[dict[str, Any]] = []
    for path in sorted(reflections_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            artifact = ReflectionArtifact.model_validate(data)
            if status is not None and artifact.status != status:
                continue
            results.append(
                {
                    "reflection_id": artifact.reflection_id,
                    "status": artifact.status.value,
                    "kind": artifact.provenance.input_artifact.kind,
                    "generated_at": artifact.provenance.generated_at,
                    "path": str(path.resolve().relative_to(Path(workspace).resolve())),
                }
            )
        except (json.JSONDecodeError, Exception):
            # Skip malformed files
            continue
    return results


def delete_artifact(
    reflection_id: str,
    workspace: str | Path = ".",
) -> None:
    """Delete a reflection artifact by ID."""
    path = _reflections_path(workspace) / f"{reflection_id}.json"
    if path.exists():
        path.unlink()
