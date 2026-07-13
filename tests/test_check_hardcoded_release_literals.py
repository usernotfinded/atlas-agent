import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from scripts.check_hardcoded_release_literals import (
    _is_active_script,
    _load_release_literals,
    _scan_file,
    main,
)


@pytest.fixture
def repo_with_drift(tmp_path, monkeypatch):
    """Create a minimal repo layout with a drifted active script."""
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    docs_dir = tmp_path / "docs" / "releases"
    docs_dir.mkdir(parents=True)

    metadata = {
        "schema_version": 1,
        "source_version": "0.6.99",
        "current_public_release": "v0.6.99",
        "next_planned_release": "v0.6.100",
    }
    (docs_dir / "release-metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )

    # Active script with hardcoded current version.
    (scripts_dir / "check_active.py").write_text(
        'PACKAGE_VERSION = "0.6.99"\n'
        'if __name__ == "__main__":\n'
        '    print("ok")\n',
        encoding="utf-8",
    )

    # Historical script should be ignored.
    (scripts_dir / "check_v0612_history.py").write_text(
        'VERSION = "0.6.99"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.REPO_ROOT", tmp_path
    )
    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.METADATA_PATH",
        docs_dir / "release-metadata.json",
    )
    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.SCRIPTS_DIR", scripts_dir
    )
    return tmp_path


@pytest.fixture
def repo_clean(tmp_path, monkeypatch):
    """Create a minimal repo layout with no drift."""
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    docs_dir = tmp_path / "docs" / "releases"
    docs_dir.mkdir(parents=True)

    metadata = {
        "schema_version": 1,
        "source_version": "0.6.99",
        "current_public_release": "v0.6.99",
        "next_planned_release": "v0.6.100",
    }
    (docs_dir / "release-metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )

    (scripts_dir / "check_active.py").write_text(
        'print("no hardcoded literals here")\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.REPO_ROOT", tmp_path
    )
    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.METADATA_PATH",
        docs_dir / "release-metadata.json",
    )
    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.SCRIPTS_DIR", scripts_dir
    )
    return tmp_path


def test_load_release_literals():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        meta_path = root / "release-metadata.json"
        meta_path.write_text(
            json.dumps(
                {
                    "source_version": "0.6.5",
                    "current_public_release": "v0.6.5",
                    "next_planned_release": "v0.6.6",
                }
            ),
            encoding="utf-8",
        )
        import scripts.check_hardcoded_release_literals as chrl

        old_path = chrl.METADATA_PATH
        chrl.METADATA_PATH = meta_path
        try:
            literals = _load_release_literals()
            assert literals == {"0.6.5", "v0.6.5", "0.6.6", "v0.6.6"}
        finally:
            chrl.METADATA_PATH = old_path


def test_is_active_script():
    assert _is_active_script(Path("scripts/check_public_docs_consistency.py"))
    assert not _is_active_script(Path("scripts/check_v0612_release_prep.py"))
    assert not _is_active_script(Path("scripts/check_v0599_history.py"))
    assert not _is_active_script(Path("scripts/README.md"))


def test_scan_file_finds_assignment():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "script.py"
        path.write_text('VERSION = "0.6.99"\n', encoding="utf-8")
        findings = _scan_file(path, {"0.6.99"})
        assert len(findings) == 1
        assert findings[0][1] == "0.6.99"


def test_scan_file_ignores_docstring():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "script.py"
        path.write_text(
            '"""Docs for 0.6.99."""\nVERSION = "other"\n',
            encoding="utf-8",
        )
        findings = _scan_file(path, {"0.6.99"})
        assert findings == []


def test_scan_file_ignores_comment():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "script.py"
        path.write_text(
            '# Version 0.6.99\nVERSION = "other"\n',
            encoding="utf-8",
        )
        findings = _scan_file(path, {"0.6.99"})
        assert findings == []


def test_main_fails_on_drift(repo_with_drift, monkeypatch):
    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.SCRIPTS_DIR",
        repo_with_drift / "scripts",
    )
    assert main() == 2


def test_main_passes_when_clean(repo_clean, monkeypatch):
    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.SCRIPTS_DIR",
        repo_clean / "scripts",
    )
    assert main() == 0
