# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_check_hardcoded_release_literals.py
# PURPOSE: Verifies check hardcoded release literals behavior and regression
#         expectations.
# DEPS:    json, re, subprocess, sys, pathlib, pytest, additional local modules.
# ==============================================================================

# --- IMPORTS ---

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_hardcoded_release_literals import (
    _is_active_script,
    _load_release_literals,
    _scan_docs_config_dirs,
    _scan_file,
    _scan_text_file,
    main,
)


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

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


@pytest.fixture
def repo_docs_drift(tmp_path, monkeypatch):
    """Create a minimal repo layout with a drifted docs/config example."""
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    docs_releases = tmp_path / "docs" / "releases"
    docs_releases.mkdir(parents=True)
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()

    metadata = {
        "schema_version": 1,
        "source_version": "0.6.99",
        "current_public_release": "v0.6.99",
        "next_planned_release": "v0.6.100",
    }
    (docs_releases / "release-metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )

    (scripts_dir / "check_active.py").write_text(
        'print("no hardcoded literals here")\n',
        encoding="utf-8",
    )

    (configs_dir / "market.example.yaml").write_text(
        'symbol: "DEMO-v0.6.99"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.REPO_ROOT", tmp_path
    )
    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.METADATA_PATH",
        docs_releases / "release-metadata.json",
    )
    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.SCRIPTS_DIR", scripts_dir
    )
    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.DOCS_CONFIG_DIRS",
        [configs_dir],
    )
    return tmp_path


def test_load_release_literals(tmp_path, monkeypatch):
    meta_path = tmp_path / "release-metadata.json"
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
    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.METADATA_PATH", meta_path
    )
    literals = _load_release_literals()
    assert literals == {"0.6.5", "v0.6.5", "0.6.6", "v0.6.6"}


def test_is_active_script():
    assert _is_active_script(Path("scripts/check_public_docs_consistency.py"))
    assert not _is_active_script(Path("scripts/check_v0612_release_prep.py"))
    assert not _is_active_script(Path("scripts/check_v0599_history.py"))
    assert not _is_active_script(Path("scripts/README.md"))


def test_scan_file_finds_assignment(tmp_path):
    path = tmp_path / "script.py"
    path.write_text('VERSION = "0.6.99"\n', encoding="utf-8")
    findings = _scan_file(path, {"0.6.99"})
    assert len(findings) == 1
    assert findings[0][1] == "0.6.99"


def test_scan_file_ignores_docstring(tmp_path):
    path = tmp_path / "script.py"
    path.write_text(
        '"""Docs for 0.6.99."""\nVERSION = "other"\n',
        encoding="utf-8",
    )
    findings = _scan_file(path, {"0.6.99"})
    assert findings == []


def test_scan_file_does_not_see_literal_in_comment(tmp_path):
    # AST scanning does not see literals that only appear in comments.
    path = tmp_path / "script.py"
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


def test_scan_text_file_finds_literal(tmp_path):
    path = tmp_path / "example.yaml"
    path.write_text(
        'symbol: "DEMO-v0.6.99"\n',
        encoding="utf-8",
    )
    pattern = re.compile("|".join(re.escape(lit) for lit in {"v0.6.99"}))
    findings = _scan_text_file(path, pattern)
    assert len(findings) == 1
    assert findings[0][1] == "v0.6.99"


def test_scan_text_file_reports_multiple_matches_per_line(tmp_path):
    path = tmp_path / "example.yaml"
    path.write_text(
        'symbols: ["DEMO-v0.6.99", "DEMO-0.6.99"]\n',
        encoding="utf-8",
    )
    pattern = re.compile("|".join(re.escape(lit) for lit in {"v0.6.99", "0.6.99"}))
    findings = _scan_text_file(path, pattern)
    literals = [finding[1] for finding in findings]
    assert "v0.6.99" in literals
    assert "0.6.99" in literals


def test_docs_config_scan_finds_literal(repo_docs_drift, monkeypatch, capsys):
    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.SCRIPTS_DIR",
        repo_docs_drift / "scripts",
    )
    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.DOCS_CONFIG_DIRS",
        [repo_docs_drift / "configs"],
    )
    assert main() == 2
    captured = capsys.readouterr().out
    assert "configs/market.example.yaml" in captured
    assert "v0.6.99" in captured


def test_docs_config_scan_passes_when_clean(repo_clean, monkeypatch):
    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.SCRIPTS_DIR",
        repo_clean / "scripts",
    )
    configs_dir = repo_clean / "configs"
    configs_dir.mkdir()
    (configs_dir / "market.example.yaml").write_text(
        'symbol: "DEMO-SYMBOL"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "scripts.check_hardcoded_release_literals.DOCS_CONFIG_DIRS",
        [configs_dir],
    )
    assert main() == 0
