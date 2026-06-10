#!/usr/bin/env python3.11
import sys
import tomllib
from pathlib import Path
from release_metadata import load_metadata, validate_metadata

def main():
    repo_root = Path(__file__).resolve().parent.parent
    metadata_path = repo_root / "docs" / "releases" / "release-metadata.json"
    
    if not metadata_path.exists():
        print(f"Error: {metadata_path} not found.")
        sys.exit(1)
        
    try:
        metadata = load_metadata(metadata_path)
    except Exception as e:
        print(f"Error parsing JSON: {e}")
        sys.exit(1)
        
    errors = validate_metadata(metadata, repo_root)
    
    # Check pyproject.toml version
    pyproject_path = repo_root / "pyproject.toml"
    try:
        with open(pyproject_path, "rb") as f:
            pyproject_data = tomllib.load(f)
        project_version = pyproject_data.get("project", {}).get("version")
        if project_version != metadata.get("source_version"):
            errors.append(f"source_version ({metadata.get('source_version')}) does not match pyproject.toml version ({project_version})")
    except Exception as e:
        errors.append(f"Failed to read pyproject.toml: {e}")
        
    if errors:
        print("Release metadata validation failed:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
        
    print("Release metadata check PASSED.")
    sys.exit(0)

if __name__ == "__main__":
    main()
