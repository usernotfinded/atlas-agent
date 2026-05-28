from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atlas_agent.research.session import (
    RESEARCH_ARTIFACT_SCHEMA_VERSION,
    RESEARCH_DIR,
    ResearchSessionError,
    UnsupportedArtifactSchemaError,
    _is_inside_workspace,
    sanitize_symbol,
    validate_run_id,
)


@dataclass(frozen=True)
class ArtifactKind:
    """Descriptor for a family of research artifacts stored on disk."""

    name: str
    id_field: str
    subdir: str | None = None
    schema_version: str = RESEARCH_ARTIFACT_SCHEMA_VERSION


@dataclass(frozen=True)
class ArtifactEntry:
    """Result of listing one artifact file."""

    path: Path
    data: dict[str, Any] | None
    is_malformed: bool
    symbol: str


class ResearchArtifactStore:
    """Centralized read/write helpers for research artifacts.

    Preserves symlink containment, schema skipping, malformed sentinels,
    workspace-relative paths, and sort order.
    """

    def __init__(self, workspace_path: Path) -> None:
        self.workspace_path = workspace_path
        self.research_dir = workspace_path / RESEARCH_DIR

    def _search_dirs(self, kind: ArtifactKind, symbol: str | None = None) -> list[Path]:
        """Return the directories that may contain artifacts of this kind."""
        if not self.research_dir.exists():
            return []

        dirs: list[Path] = []
        if symbol is not None:
            safe = sanitize_symbol(symbol)
            sym_dir = self.research_dir / safe
            if kind.subdir:
                dirs.append(sym_dir / kind.subdir)
            else:
                dirs.append(sym_dir)
        else:
            for sym_dir in self.research_dir.iterdir():
                if not sym_dir.is_dir():
                    continue
                if kind.subdir:
                    sub = sym_dir / kind.subdir
                    if sub.exists():
                        dirs.append(sub)
                else:
                    dirs.append(sym_dir)
        return dirs

    def list_entries(
        self,
        kind: ArtifactKind,
        symbol: str | None = None,
    ) -> list[ArtifactEntry]:
        """List artifact entries with common safety and parsing logic.

        Malformed JSON is returned as ``is_malformed=True`` with ``data=None``.
        Unsupported schema versions are skipped entirely in list mode.
        Symlinks escaping the workspace are skipped.
        """
        entries: list[ArtifactEntry] = []
        for directory in self._search_dirs(kind, symbol=symbol):
            if not directory.exists():
                continue
            # Determine symbol from directory path
            if kind.subdir:
                sym = directory.parent.name
            else:
                sym = directory.name
            for path in directory.glob("*.json"):
                if not path.is_file():
                    continue
                if path.is_symlink() and not _is_inside_workspace(path, self.workspace_path):
                    continue
                try:
                    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    entries.append(ArtifactEntry(path, None, True, sym))
                    continue
                sv = data.get("schema_version")
                if sv is not None and sv != kind.schema_version:
                    continue
                entries.append(ArtifactEntry(path, data, False, sym))
        return entries

    def load_artifact(
        self,
        path: Path,
        *,
        artifact_type: str,
    ) -> dict[str, Any]:
        """Load a single artifact JSON safely.

        Fail-closed: missing, malformed, unsupported schema, or unsafe symlink
        all raise ``ResearchSessionError`` or ``UnsupportedArtifactSchemaError``.
        """
        if not path.exists() or not path.is_file():
            raise ResearchSessionError("artifact_not_found")
        if path.is_symlink() and not _is_inside_workspace(path, self.workspace_path):
            raise ResearchSessionError("artifact_path_not_allowed")
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            raise ResearchSessionError("artifact_malformed")
        data["artifact_path"] = path.relative_to(self.workspace_path).as_posix()
        sv = data.get("schema_version")
        if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
            raise UnsupportedArtifactSchemaError(f"unsupported_{artifact_type}_artifact_schema")
        return data

    def find_by_id(self, kind: ArtifactKind, artifact_id: str) -> Path | None:
        """Find exactly one artifact by its ID.

        Returns the path, or ``None`` if not found.
        Raises ``ResearchSessionError`` if ambiguous.
        """
        safe_id = validate_run_id(artifact_id)
        if not self.research_dir.exists():
            return None

        matches: list[Path] = []
        for directory in self.research_dir.iterdir():
            if not directory.is_dir():
                continue
            if kind.subdir:
                candidate_dir = directory / kind.subdir
                if not candidate_dir.exists():
                    continue
            else:
                candidate_dir = directory
            candidate = candidate_dir / f"{safe_id}.json"
            if candidate.exists() and candidate.is_file():
                if candidate.is_symlink() and not _is_inside_workspace(candidate, self.workspace_path):
                    continue
                matches.append(candidate)

        if len(matches) == 0:
            return None
        if len(matches) > 1:
            raise ResearchSessionError(f"ambiguous_{kind.name}_id")
        return matches[0]

    def write_artifact(
        self,
        kind: ArtifactKind,
        symbol: str,
        artifact_id: str,
        data: dict[str, Any],
    ) -> Path:
        """Write an artifact JSON to the correct directory.

        Creates parent directories as needed. Returns the written path.
        """
        safe = sanitize_symbol(symbol)
        safe_id = validate_run_id(artifact_id)
        directory = self.research_dir / safe
        if kind.subdir:
            directory = directory / kind.subdir
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{safe_id}.json"
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        return path
