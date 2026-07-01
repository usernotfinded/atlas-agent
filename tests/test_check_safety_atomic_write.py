"""Tests for the CAND-010 safety atomic-write regression guard.

Documentation/test-only. No execution code, no network calls,
no credentials, no provider SDKs, no broker changes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER_SCRIPT = REPO_ROOT / "scripts" / "check_safety_atomic_write.py"
GUARDED_FILES = {
    "heartbeat.py": REPO_ROOT / "src" / "atlas_agent" / "safety" / "heartbeat.py",
    "deadman.py": REPO_ROOT / "src" / "atlas_agent" / "safety" / "deadman.py",
    "kill_switch.py": REPO_ROOT / "src" / "atlas_agent" / "safety" / "kill_switch.py",
    "state.py": REPO_ROOT / "src" / "atlas_agent" / "safety" / "state.py",
}
HELPER_FILE = REPO_ROOT / "src" / "atlas_agent" / "safety" / "atomic_write.py"


def _run_checker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER_SCRIPT), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def _build_tmp_repo(tmp_path: Path, *, omit: str | None = None) -> Path:
    repo = tmp_path / "repo"
    target = repo / "src" / "atlas_agent" / "safety"
    target.mkdir(parents=True)
    for name, src in GUARDED_FILES.items():
        if name == omit:
            continue
        dst = target / name
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    helper_dst = target / "atomic_write.py"
    helper_dst.write_text(HELPER_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    return repo


def _inject_regression(repo: Path, filename: str, regression: str) -> None:
    target = repo / "src" / "atlas_agent" / "safety" / filename
    original = target.read_text(encoding="utf-8")
    injected = original + f"\n# injected regression\n{regression}\n"
    target.write_text(injected, encoding="utf-8")


class TestCheckerExists:
    def test_script_exists_and_is_executable(self) -> None:
        assert CHECKER_SCRIPT.exists(), f"Checker not found: {CHECKER_SCRIPT}"
        text = CHECKER_SCRIPT.read_text(encoding="utf-8")
        assert text.startswith("#!/usr/bin/env python3"), "Checker missing python3 shebang"


class TestCheckerPassesOnCurrentRepo:
    def test_checker_passes(self) -> None:
        result = _run_checker()
        assert result.returncode == 0, (
            f"Checker failed:\n{result.stdout}\n{result.stderr}"
        )
        assert "PASSED" in result.stdout

    def test_checker_accepts_positional_root(self) -> None:
        result = _run_checker(str(REPO_ROOT))
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASSED" in result.stdout

    def test_checker_accepts_repo_root_flag(self) -> None:
        result = _run_checker("--repo-root", str(REPO_ROOT))
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASSED" in result.stdout


class TestCheckerFailsInjectedRegressions:
    @pytest.mark.parametrize("filename", list(GUARDED_FILES.keys()))
    def test_injected_with_suffix_tmp_fails(self, tmp_path: Path, filename: str) -> None:
        # Build the regression string dynamically so the literal forbidden
        # pattern does not appear in this test source.
        suffix = '"' + '.tmp"'
        regression = f"tmp_path = target.with_suffix(target.suffix + {suffix})"
        repo = _build_tmp_repo(tmp_path)
        _inject_regression(repo, filename, regression)

        result = _run_checker(str(repo))
        assert result.returncode == 2, (
            f"Expected violation exit 2, got {result.returncode}:\n"
            f"{result.stdout}\n{result.stderr}"
        )
        assert filename in result.stdout
        assert "fixed with_suffix .tmp pattern" in result.stdout

    def test_injected_literal_json_tmp_fails(self, tmp_path: Path) -> None:
        suffix = '"' + '.json.tmp"'
        regression = f"tmp_path = target.parent / (target.name + {suffix})"
        repo = _build_tmp_repo(tmp_path)
        _inject_regression(repo, "state.py", regression)

        result = _run_checker(str(repo))
        assert result.returncode == 2
        assert "state.py" in result.stdout
        assert "literal .json.tmp" in result.stdout


class TestCheckerOutputFormat:
    def test_output_includes_file_and_line(self, tmp_path: Path) -> None:
        suffix = '"' + '.tmp"'
        regression = f"tmp_path = target.with_suffix(target.suffix + {suffix})"
        repo = _build_tmp_repo(tmp_path)
        _inject_regression(repo, "heartbeat.py", regression)

        result = _run_checker(str(repo))
        assert result.returncode == 2
        assert "heartbeat.py:" in result.stdout
        # Line number should appear after the colon.
        assert any(
            ch.isdigit()
            for ch in result.stdout.split("heartbeat.py:", 1)[1].split(":", 1)[0]
        )


class TestCheckerExitCodes:
    def test_exits_1_for_invalid_repo_root(self) -> None:
        result = _run_checker("/nonexistent/path/that/does/not/exist")
        assert result.returncode == 1

    def test_exits_1_for_missing_guarded_file(self, tmp_path: Path) -> None:
        repo = _build_tmp_repo(tmp_path, omit="state.py")
        result = _run_checker(str(repo))
        assert result.returncode == 1
        assert "missing file" in (result.stdout + result.stderr).lower()

    def test_exits_2_for_violation(self, tmp_path: Path) -> None:
        suffix = '"' + '.tmp"'
        regression = f"tmp_path = target.with_suffix(target.suffix + {suffix})"
        repo = _build_tmp_repo(tmp_path)
        _inject_regression(repo, "heartbeat.py", regression)
        result = _run_checker(str(repo))
        assert result.returncode == 2


class TestCheckerDoesNotFlagHelper:
    def test_atomic_write_helper_is_allowed(self) -> None:
        # Running the checker on the real repo already passes, which implies
        # atomic_write.py is allowed. This test makes that explicit.
        result = _run_checker()
        assert result.returncode == 0
        assert "atomic_write.py" not in result.stdout


class TestCheckerSafety:
    def test_no_network_calls_in_checker(self) -> None:
        text = CHECKER_SCRIPT.read_text(encoding="utf-8")
        assert "import requests" not in text
        assert "import urllib" not in text
        assert "import httpx" not in text
        assert "import socket" not in text

    def test_no_credential_loading_in_checker(self) -> None:
        text = CHECKER_SCRIPT.read_text(encoding="utf-8")
        assert "load_dotenv" not in text
        assert "os.environ" not in text
        assert "environ[" not in text
        assert "getenv(" not in text


class TestExistingCAND009TestsStillPass:
    def test_cand009_safety_tests_pass(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/safety/test_atomic_write.py",
                "tests/safety/test_heartbeat.py",
                "tests/safety/test_deadman.py",
                "tests/safety/test_safety_state.py",
                "tests/safety/test_kill_switch_core.py",
                "-q",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
