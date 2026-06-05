"""Local storage for learning suggestion artifacts.

Stores suggestions under `.atlas/learning/suggestions/` as JSON files.
All operations are local and safe.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from atlas_agent.learning.models import LearningSuggestion, SuggestionStatus


SUGGESTIONS_DIR = ".atlas/learning/suggestions"


def _suggestions_path(workspace: str | Path = ".") -> Path:
    return Path(workspace) / SUGGESTIONS_DIR


def save_suggestion(
    suggestion: LearningSuggestion,
    workspace: str | Path = ".",
) -> Path:
    """Persist a learning suggestion to local storage."""
    suggestions_dir = _suggestions_path(workspace)
    suggestions_dir.mkdir(parents=True, exist_ok=True)
    path = suggestions_dir / f"{suggestion.suggestion_id}.json"
    path.write_text(
        json.dumps(suggestion.model_dump(mode="json"), indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path


def load_suggestion(
    suggestion_id: str,
    workspace: str | Path = ".",
) -> LearningSuggestion:
    """Load a learning suggestion by ID."""
    path = _suggestions_path(workspace) / f"{suggestion_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Learning suggestion not found: {suggestion_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return LearningSuggestion.model_validate(data)


def list_suggestions(
    workspace: str | Path = ".",
    status: SuggestionStatus | None = None,
) -> list[dict[str, Any]]:
    """List learning suggestions, optionally filtered by status.

    Returns metadata dicts sorted newest-first.
    """
    suggestions_dir = _suggestions_path(workspace)
    if not suggestions_dir.exists():
        return []

    results: list[dict[str, Any]] = []
    for path in sorted(suggestions_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            suggestion = LearningSuggestion.model_validate(data)
            if status is not None and suggestion.status != status:
                continue
            results.append(
                {
                    "suggestion_id": suggestion.suggestion_id,
                    "status": suggestion.status.value,
                    "title": suggestion.title,
                    "kind": suggestion.kind,
                    "created_at": suggestion.audit.created_at,
                    "path": str(path.resolve().relative_to(Path(workspace).resolve())),
                }
            )
        except (json.JSONDecodeError, Exception):
            # Skip malformed files
            continue
    return results


def delete_suggestion(
    suggestion_id: str,
    workspace: str | Path = ".",
) -> None:
    """Delete a learning suggestion by ID."""
    path = _suggestions_path(workspace) / f"{suggestion_id}.json"
    if path.exists():
        path.unlink()
