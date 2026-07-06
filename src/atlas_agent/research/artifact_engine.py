"""Small internal helpers for pilot research artifact mechanics.

This module is intentionally narrow for CAND-014 Phase 2. It has no registry,
no provider integration, no CLI coupling, and no import-time side effects.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atlas_agent.research.sandbox_contracts import canonical_json_dumps


@dataclass(frozen=True)
class ArtifactSpec:
    artifact_type: str
    artifact_directory: str
    hash_excluded_fields: frozenset[str]


def artifact_hash_payload(data: dict[str, Any], spec: ArtifactSpec) -> dict[str, Any]:
    return {k: v for k, v in data.items() if k not in spec.hash_excluded_fields}


def artifact_sha256(data: dict[str, Any], spec: ArtifactSpec) -> str:
    canonical = canonical_json_dumps(artifact_hash_payload(data, spec))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_json_object(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json_object(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def build_artifact_path(
    workspace_path: Path,
    research_dir: str,
    symbol: str,
    spec: ArtifactSpec,
    artifact_id: str,
) -> Path:
    symbol_dir = symbol.replace("/", "_")
    return workspace_path / research_dir / symbol_dir / spec.artifact_directory / f"{artifact_id}.json"


def list_artifact_json_paths(
    workspace_path: Path,
    research_dir: str,
    spec: ArtifactSpec,
    symbol: str | None = None,
) -> list[Path]:
    search_dir = workspace_path / research_dir
    if symbol:
        result_dir = search_dir / symbol / spec.artifact_directory
        if not result_dir.exists():
            return []
        return list(result_dir.glob("*.json"))
    return list(search_dir.rglob(f"{spec.artifact_directory}/*.json"))
