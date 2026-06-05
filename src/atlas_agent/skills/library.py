"""Local skill library storage.

Stores promoted skills under `.atlas/skills/library/` as JSON files.
All operations are local and safe.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from atlas_agent.skills.models import SkillLibraryEntry


SKILLS_LIBRARY_DIR = ".atlas/skills/library"


def _library_path(workspace: str | Path = ".") -> Path:
    return Path(workspace) / SKILLS_LIBRARY_DIR


def save_skill(
    entry: SkillLibraryEntry,
    workspace: str | Path = ".",
) -> Path:
    """Persist a skill library entry to local storage."""
    library_dir = _library_path(workspace)
    library_dir.mkdir(parents=True, exist_ok=True)
    path = library_dir / f"{entry.skill_id}.json"
    path.write_text(
        json.dumps(entry.model_dump(mode="json"), indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path


def load_skill(
    skill_id: str,
    workspace: str | Path = ".",
) -> SkillLibraryEntry:
    """Load a skill library entry by ID."""
    path = _library_path(workspace) / f"{skill_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Skill not found: {skill_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return SkillLibraryEntry.model_validate(data)


def list_skills(
    workspace: str | Path = ".",
) -> list[dict[str, Any]]:
    """List promoted skills in the library.

    Returns metadata dicts sorted newest-first.
    """
    library_dir = _library_path(workspace)
    if not library_dir.exists():
        return []

    results: list[dict[str, Any]] = []
    for path in sorted(library_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            entry = SkillLibraryEntry.model_validate(data)
            results.append(
                {
                    "skill_id": entry.skill_id,
                    "title": entry.title,
                    "kind": entry.kind,
                    "source_candidate_id": entry.source_candidate_id,
                    "created_at": entry.created_at,
                    "path": str(path.resolve().relative_to(Path(workspace).resolve())),
                }
            )
        except (json.JSONDecodeError, Exception):
            continue
    return results


def delete_skill(
    skill_id: str,
    workspace: str | Path = ".",
) -> None:
    """Delete a skill library entry by ID."""
    path = _library_path(workspace) / f"{skill_id}.json"
    if path.exists():
        path.unlink()
