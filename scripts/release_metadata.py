# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/release_metadata.py
# PURPOSE: Implements repository tooling for release metadata.
# DEPS:    json, pathlib, typing.
# ==============================================================================

# --- IMPORTS ---

import json
from pathlib import Path
from typing import Dict, Any, List, Optional

# ==============================================================================
# SCRIPT IMPLEMENTATION
# ==============================================================================

# --- HELPERS AND ENTRYPOINTS ---

class ReleaseMetadata:
    def __init__(self, data: Dict[str, Any]):
        self.data = data

    @property
    def source_version(self) -> str:
        return self.data.get("source_version", "")

    @property
    def current_public_release(self) -> str:
        return self.data.get("current_public_release", "")

    @property
    def next_planned_release(self) -> str:
        return self.data.get("next_planned_release", "")

    @property
    def historical_stable_baseline(self) -> str:
        return self.data.get("historical_stable_baseline", "")

    @property
    def pypi_published(self) -> bool:
        return self.data.get("pypi_published", False)

    @property
    def releases(self) -> List[Dict[str, Any]]:
        return self.data.get("releases", [])

    @property
    def current_public_release_record(self) -> Optional[Dict[str, Any]]:
        for r in self.releases:
            if r.get("status") == "current_public":
                return r
        return None

    @property
    def prepared_releases(self) -> List[Dict[str, Any]]:
        return [r for r in self.releases if r.get("status") == "prepared"]

    def release_by_tag(self, tag: str) -> Optional[Dict[str, Any]]:
        for r in self.releases:
            if r.get("tag") == tag:
                return r
        return None


def load_metadata(path: Path) -> Dict[str, Any]:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def validate_metadata(metadata: Dict[str, Any], project_root: Path) -> list[str]:
    errors = []
    
    if metadata.get("schema_version") != 1:
        errors.append(f"Unsupported schema version: {metadata.get('schema_version')}")
        
    source_version = metadata.get("source_version")
    if not source_version:
        errors.append("Missing source_version")
        
    current_public_release = metadata.get("current_public_release")
    if not current_public_release:
        errors.append("Missing current_public_release")
        
    releases = metadata.get("releases", [])
    if not releases:
        errors.append("No releases found")
        
    current_public_count = 0
    current_public_found = False
    
    for release in releases:
        status = release.get("status")
        if status == "current_public":
            current_public_count += 1
            if release.get("tag") == current_public_release:
                current_public_found = True
                
        if status in ("current_public", "prepared"):
            rn = release.get("release_notes")
            if not rn or not (project_root / rn).exists():
                errors.append(f"Missing release notes for {release.get('tag')}: {rn}")
                
            ts = release.get("trust_status")
            if not ts or not (project_root / ts).exists():
                errors.append(f"Missing trust status for {release.get('tag')}: {ts}")
                
        if status == "current_public" and not release.get("github_release"):
            errors.append(f"Release {release.get('tag')} is current_public but github_release is false")
            
    if current_public_count != 1:
        errors.append(f"Expected exactly 1 current_public release, found {current_public_count}")
        
    if not current_public_found:
        errors.append(f"current_public_release '{current_public_release}' not found in releases with status 'current_public'")
        
    return errors
