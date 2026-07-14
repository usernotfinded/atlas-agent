import json
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent

# Make scripts/ importable for release_metadata without relying on PYTHONPATH.
_SCRIPTS_DIR = str(ROOT / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from release_metadata import load_metadata, ReleaseMetadata


@pytest.fixture
def release_identity():
    """Load release identity from metadata and return current-state values.

    Returns a dict with:
      - source_version (e.g. "0.6.25")
      - current_public_release (e.g. "v0.6.25")
      - next_planned_release (e.g. "v0.6.26")
      - previous_public_release (first historical release tag, e.g. "v0.6.24")
    """
    metadata = ReleaseMetadata(
        load_metadata(ROOT / "docs" / "releases" / "release-metadata.json")
    )
    previous_public_release = None
    for release in metadata.releases:
        if release.get("status") == "historical":
            previous_public_release = release.get("tag")
            break
    return {
        "source_version": metadata.source_version,
        "current_public_release": metadata.current_public_release,
        "next_planned_release": metadata.next_planned_release,
        "previous_public_release": previous_public_release,
    }


@pytest.fixture
def write_complete_setup_config():
    def _write(workspace: Path, provider="anthropic", model="claude-opus-4-7"):
        atlas_dir = workspace / ".atlas"
        atlas_dir.mkdir(parents=True, exist_ok=True)
        config_file = atlas_dir / "config.json"
        config_data = {
            "setup_mode": "quick",
            "provider": provider,
            "model": model,
            "messaging": "cli",
            "workspace_path": str(workspace),
            "trust_mode": "paper",
            "broker_mode": "paper",
            "update_channel": "stable",
            "credentials_configured": True
        }
        with open(config_file, "w") as f:
            json.dump(config_data, f)
        
        # Also satisfy credential requirement
        env_atlas = workspace / ".env.atlas"
        env_atlas.write_text(f"ANTHROPIC_API_KEY=test-key\n", encoding="utf-8")
        return config_data
    return _write
