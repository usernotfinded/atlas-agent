"""Local storage for skill candidate artifacts.

Stores candidates under `.atlas/skill_candidates/` as JSON files.
All operations are local and safe.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from atlas_agent.skills.models import SkillCandidate, SkillCandidateStatus


CANDIDATES_DIR = ".atlas/skill_candidates"


def _candidates_path(workspace: str | Path = ".") -> Path:
    return Path(workspace) / CANDIDATES_DIR


def save_candidate(
    candidate: SkillCandidate,
    workspace: str | Path = ".",
) -> Path:
    """Persist a skill candidate to local storage."""
    candidates_dir = _candidates_path(workspace)
    candidates_dir.mkdir(parents=True, exist_ok=True)
    path = candidates_dir / f"{candidate.candidate_id}.json"
    path.write_text(
        json.dumps(candidate.model_dump(mode="json"), indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path


def load_candidate(
    candidate_id: str,
    workspace: str | Path = ".",
) -> SkillCandidate:
    """Load a skill candidate by ID."""
    path = _candidates_path(workspace) / f"{candidate_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Skill candidate not found: {candidate_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return SkillCandidate.model_validate(data)


def list_candidates(
    workspace: str | Path = ".",
    status: SkillCandidateStatus | None = None,
) -> list[dict[str, Any]]:
    """List skill candidates, optionally filtered by status.

    Returns metadata dicts sorted newest-first.
    """
    candidates_dir = _candidates_path(workspace)
    if not candidates_dir.exists():
        return []

    results: list[dict[str, Any]] = []
    for path in sorted(candidates_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            candidate = SkillCandidate.model_validate(data)
            if status is not None and candidate.status != status:
                continue
            results.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "status": candidate.status.value,
                    "title": candidate.title,
                    "kind": candidate.kind,
                    "created_at": candidate.audit.created_at,
                    "path": str(path.resolve().relative_to(Path(workspace).resolve())),
                }
            )
        except (json.JSONDecodeError, Exception):
            continue
    return results


def delete_candidate(
    candidate_id: str,
    workspace: str | Path = ".",
) -> None:
    """Delete a skill candidate by ID."""
    path = _candidates_path(workspace) / f"{candidate_id}.json"
    if path.exists():
        path.unlink()
