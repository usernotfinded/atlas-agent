"""Tests for check_runtime_diagnostics.py."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


def _run_script(*args: str) -> subprocess.CompletedProcess:
    repo_root = Path(__file__).resolve().parent.parent
    script_path = repo_root / "scripts" / "check_runtime_diagnostics.py"
    result = subprocess.run(
        [sys.executable, str(script_path), *args],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    return result


class TestCheckRuntimeDiagnostics:
    def test_runs_successfully(self) -> None:
        result = _run_script()
        assert result.returncode == 0

    def test_includes_core_checks(self) -> None:
        result = _run_script()
        assert "dev_check.sh" in result.stdout
        assert "ci_check.sh" in result.stdout
        assert "release_check.sh --quick" in result.stdout

    def test_includes_long_checks(self) -> None:
        result = _run_script()
        assert "research_check.sh" in result.stdout
        assert "release_check.sh --full" in result.stdout

    def test_includes_focused_subsets(self) -> None:
        result = _run_script()
        assert "Focused subsets" in result.stdout
        assert "pytest" in result.stdout

    def test_includes_timeout_guidance(self) -> None:
        result = _run_script()
        assert "WARN" in result.stdout or "INCONCLUSIVE" in result.stdout
        assert "core gates pass" in result.stdout.lower() or "core checks pass" in result.stdout.lower()

    def test_includes_environment_hints(self) -> None:
        result = _run_script()
        assert "ATLAS_CHECK_FAIL_FAST" in result.stdout

    def test_does_not_run_checks(self) -> None:
        result = _run_script()
        assert "passed" not in result.stdout.lower() or "elapsed" in result.stdout.lower()
        # The script should not invoke pytest or other check scripts.
        assert "pytest -q" not in result.stdout

    def test_json_output_valid(self) -> None:
        result = _run_script("--json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["artifact_type"] == "runtime_diagnostics"
        assert data["schema_version"] == 1
        assert isinstance(data["commands"], list)
        assert isinstance(data["focused_subsets"], list)
        assert isinstance(data["environment_hints"], list)
        assert "guidance" in data

    def test_json_includes_long_check_category(self) -> None:
        result = _run_script("--json")
        data = json.loads(result.stdout)
        categories = {cmd["category"] for cmd in data["commands"]}
        assert "long" in categories
        assert "core" in categories

    def test_no_broad_or_true_in_source(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        content = (repo_root / "scripts" / "check_runtime_diagnostics.py").read_text(
            encoding="utf-8"
        )
        # The script may mention || true in guidance text; ensure it is not
        # used as a shell pattern at end of a command line.
        lines = content.splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.endswith("|| true"):
                pytest.fail(f"Found broad || true pattern in line: {line}")

    def test_no_network_calls(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        content = (repo_root / "scripts" / "check_runtime_diagnostics.py").read_text(
            encoding="utf-8"
        )
        assert "urllib" not in content
        assert "requests" not in content
        assert "httpx" not in content
