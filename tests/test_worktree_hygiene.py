from __future__ import annotations

import subprocess

import pytest

from scripts.check_no_protected_staged import (
    StagedFilesError,
    find_protected_paths,
    get_staged_paths,
    is_protected_path,
    main,
)


@pytest.mark.parametrize(
    "path,expected",
    [
        ("AUDIT_ENHANCEMENTS_2026-05-13.md", True),
        ("BATCH2_PLAN.md", True),
        ("memory/kill_switch_state.json.lock", True),
        ("build/lib/file.py", True),
        ("dist/pkg.whl", True),
        ("atlas_agent.egg-info/PKG-INFO", True),
        (".pytest_cache/cache", True),
        ("src/module/__pycache__/x.pyc", True),
        ("docs/releases/v0.5.7.dev3.md", False),
        ("scripts/smoke_package_build.sh", False),
        ("tests/test_output_safety.py", False),
        ("src/atlas_agent/redaction.py", False),
        ("data/sample/ohlcv.csv", False),
    ],
)
def test_is_protected_path(path: str, expected: bool) -> None:
    assert is_protected_path(path) is expected


def test_find_protected_paths() -> None:
    paths = [
        "AUDIT_ENHANCEMENTS_2026-05-13.md",
        "docs/releases/v0.5.7.dev3.md",
        "build/lib/file.py",
        "src/atlas_agent/redaction.py",
    ]
    assert find_protected_paths(paths) == [
        "AUDIT_ENHANCEMENTS_2026-05-13.md",
        "build/lib/file.py",
    ]


def test_find_protected_paths_empty() -> None:
    assert find_protected_paths([]) == []


def test_main_no_protected_files(capsys: pytest.CaptureFixture[str]) -> None:
    result = main(staged_paths=["docs/releases/v0.5.7.dev3.md", "src/atlas_agent/redaction.py"])
    assert result == 0
    captured = capsys.readouterr()
    assert "No protected staged files detected." in captured.out


def test_main_protected_files(capsys: pytest.CaptureFixture[str]) -> None:
    result = main(
        staged_paths=["AUDIT_ENHANCEMENTS_2026-05-13.md", "src/atlas_agent/redaction.py"]
    )
    assert result == 2
    captured = capsys.readouterr()
    assert "Protected staged files detected:" in captured.out
    assert "AUDIT_ENHANCEMENTS_2026-05-13.md" in captured.out


def test_main_multiple_protected_files(capsys: pytest.CaptureFixture[str]) -> None:
    result = main(staged_paths=["BATCH2_PLAN.md", "build/lib/file.py", "dist/out.whl"])
    assert result == 2
    captured = capsys.readouterr()
    assert "BATCH2_PLAN.md" in captured.out
    assert "build/lib/file.py" in captured.out
    assert "dist/out.whl" in captured.out


def test_main_git_failure(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = main()
    assert result == 2
    captured = capsys.readouterr()
    assert "unable to read staged files" in captured.err


def test_release_check_includes_protected_staged_check() -> None:
    content = open("scripts/release_check.sh", encoding="utf-8").read()
    assert "scripts/check_no_protected_staged.py" in content
