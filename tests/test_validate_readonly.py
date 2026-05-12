from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from atlas_agent.cli import main

@pytest.fixture
def clean_workspace():
    temp_dir = tempfile.mkdtemp()
    original_cwd = os.getcwd()
    os.chdir(temp_dir)
    try:
        main(["init", ".", "--template", "routine-trader"])
        yield Path(temp_dir)
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(temp_dir)

def test_validate_is_read_only(clean_workspace, capsys):
    def get_file_list(d: Path) -> set[str]:
        return {str(p.relative_to(d)) for p in d.rglob("*") if p.is_file()}

    files_before = get_file_list(clean_workspace)
    
    code = main(["validate"])
    assert code == 0
    _ = capsys.readouterr()
    
    files_after = get_file_list(clean_workspace)
    assert files_before == files_after, "validate created files"

def test_validate_json_is_read_only(clean_workspace, capsys):
    def get_file_list(d: Path) -> set[str]:
        return {str(p.relative_to(d)) for p in d.rglob("*") if p.is_file()}

    files_before = get_file_list(clean_workspace)
    
    code = main(["validate", "--json"])
    assert code == 0
    _ = capsys.readouterr()
    
    files_after = get_file_list(clean_workspace)
    assert files_before == files_after, "validate --json created files"
