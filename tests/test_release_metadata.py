import pytest
from pathlib import Path
from scripts.release_metadata import validate_metadata

def test_validate_metadata_valid(tmp_path):
    (tmp_path / "docs" / "releases").mkdir(parents=True)
    (tmp_path / "docs" / "trust").mkdir(parents=True)
    
    rn1 = tmp_path / "docs" / "releases" / "v0.6.8.md"
    rn1.touch()
    ts1 = tmp_path / "docs" / "trust" / "v0.6.8-status.md"
    ts1.touch()
    
    rn2 = tmp_path / "docs" / "releases" / "v0.6.7.md"
    rn2.touch()
    ts2 = tmp_path / "docs" / "trust" / "v0.6.7-status.md"
    ts2.touch()

    metadata = {
        "schema_version": 1,
        "source_version": "0.6.8",
        "current_public_release": "v0.6.7",
        "releases": [
            {
                "tag": "v0.6.8",
                "status": "prepared",
                "release_notes": "docs/releases/v0.6.8.md",
                "trust_status": "docs/trust/v0.6.8-status.md",
                "github_release": False
            },
            {
                "tag": "v0.6.7",
                "status": "current_public",
                "release_notes": "docs/releases/v0.6.7.md",
                "trust_status": "docs/trust/v0.6.7-status.md",
                "github_release": True
            }
        ]
    }
    errors = validate_metadata(metadata, tmp_path)
    assert not errors

def test_validate_metadata_missing_release_notes(tmp_path):
    metadata = {
        "schema_version": 1,
        "source_version": "0.6.8",
        "current_public_release": "v0.6.8",
        "releases": [
            {
                "tag": "v0.6.8",
                "status": "current_public",
                "release_notes": "docs/releases/v0.6.8.md",
                "trust_status": "docs/trust/v0.6.8-status.md",
                "github_release": True
            }
        ]
    }
    errors = validate_metadata(metadata, tmp_path)
    assert any("Missing release notes" in err for err in errors)

def test_validate_metadata_multiple_current_public(tmp_path):
    (tmp_path / "docs" / "releases").mkdir(parents=True)
    (tmp_path / "docs" / "trust").mkdir(parents=True)
    
    rn1 = tmp_path / "docs" / "releases" / "v0.6.8.md"
    rn1.touch()
    ts1 = tmp_path / "docs" / "trust" / "v0.6.8-status.md"
    ts1.touch()
    
    rn2 = tmp_path / "docs" / "releases" / "v0.6.7.md"
    rn2.touch()
    ts2 = tmp_path / "docs" / "trust" / "v0.6.7-status.md"
    ts2.touch()

    metadata = {
        "schema_version": 1,
        "source_version": "0.6.8",
        "current_public_release": "v0.6.8",
        "releases": [
            {
                "tag": "v0.6.8",
                "status": "current_public",
                "release_notes": "docs/releases/v0.6.8.md",
                "trust_status": "docs/trust/v0.6.8-status.md",
                "github_release": True
            },
            {
                "tag": "v0.6.7",
                "status": "current_public",
                "release_notes": "docs/releases/v0.6.7.md",
                "trust_status": "docs/trust/v0.6.7-status.md",
                "github_release": True
            }
        ]
    }
    errors = validate_metadata(metadata, tmp_path)
    assert any("Expected exactly 1 current_public release" in err for err in errors)
