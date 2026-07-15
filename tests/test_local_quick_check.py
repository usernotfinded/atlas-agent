# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_local_quick_check.py
# PURPOSE: Verifies local quick check behavior and regression expectations.
# DEPS:    os, subprocess, pathlib, pytest.
# ==============================================================================

"""Tests for local quick check and smoke check scripts."""

# --- IMPORTS ---

import os
import subprocess
from pathlib import Path

import pytest


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _run_shell(script_path: Path, cwd: Path | None = None, env: dict | None = None, args: list[str] | None = None) -> subprocess.CompletedProcess:
    cmd = ["/bin/bash", str(script_path)]
    if args:
        cmd.extend(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )
    return result


def _script_path(name: str) -> Path:
    repo_root = Path(__file__).resolve().parent.parent
    return repo_root / "scripts" / name


@pytest.fixture(scope="module")
def smoke_check_result() -> subprocess.CompletedProcess:
    return _run_shell(_script_path("smoke_check.sh"))


@pytest.fixture(scope="module")
def local_quick_check_result() -> subprocess.CompletedProcess:
    return _run_shell(_script_path("local_quick_check.sh"))


class TestSmokeCheckSh:
    def test_file_exists_and_is_executable(self) -> None:
        path = _script_path("smoke_check.sh")
        assert path.exists()
        assert os.access(path, os.X_OK)

    def test_uses_python_env_resolver(self) -> None:
        text = _script_path("smoke_check.sh").read_text(encoding="utf-8")
        assert 'source "$SCRIPT_DIR/python_env.sh"' in text
        assert 'resolve_python_bin' in text
        assert 'require_python_311' in text

    def test_contains_no_forbidden_commands(self) -> None:
        text = _script_path("smoke_check.sh").read_text(encoding="utf-8")
        forbidden = [
            "twine upload",
            "python -m twine upload",
            "gh release create",
            "git push --tags",
            "git tag",
            "git push --force",
            "git push --force-with-lease",
            "git reset --hard",
            "git clean",
            "git stash pop",
            "git stash drop",
            "git stash clear",
        ]
        for cmd in forbidden:
            assert cmd not in text, f"Found forbidden command: {cmd}"

    def test_contains_safety_checks(self) -> None:
        text = _script_path("smoke_check.sh").read_text(encoding="utf-8")
        assert "check_forbidden_claims.py" in text
        assert "check_submit_execution_safety.py" in text
        assert "check_no_protected_staged.py" in text
        assert "git diff --check" in text

    def test_contains_demo_command_smoke_check(self) -> None:
        text = _script_path("smoke_check.sh").read_text(encoding="utf-8")
        assert "check_demo_command_smoke.py" in text

    def test_contains_no_provider_or_broker_calls(self) -> None:
        text = _script_path("smoke_check.sh").read_text(encoding="utf-8")
        assert "alpaca" not in text.lower()
        assert "binance" not in text.lower()
        assert "openai" not in text.lower()
        assert "anthropic" not in text.lower()

    @pytest.mark.slow
    def test_runs_successfully(self, smoke_check_result) -> None:
        result = smoke_check_result
        assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert "All smoke checks passed" in result.stdout

    @pytest.mark.slow
    def test_respects_fail_fast_env(self) -> None:
        env = os.environ.copy()
        env["ATLAS_CHECK_FAIL_FAST"] = "1"
        env["ATLAS_CHECK_PYTEST_ARGS"] = "--collect-only"
        result = _run_shell(_script_path("smoke_check.sh"), env=env)
        assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert "All smoke checks passed" in result.stdout

    def test_prints_reminder_about_full_gate(self, smoke_check_result) -> None:
        result = smoke_check_result
        assert "release_check.sh --full" in result.stdout


class TestLocalQuickCheckSh:
    def test_file_exists_and_is_executable(self) -> None:
        path = _script_path("local_quick_check.sh")
        assert path.exists()
        assert os.access(path, os.X_OK)

    def test_uses_python_env_resolver(self) -> None:
        text = _script_path("local_quick_check.sh").read_text(encoding="utf-8")
        assert 'source "$SCRIPT_DIR/python_env.sh"' in text
        assert 'resolve_python_bin' in text
        assert 'require_python_311' in text

    def test_contains_no_forbidden_commands(self) -> None:
        text = _script_path("local_quick_check.sh").read_text(encoding="utf-8")
        forbidden = [
            "twine upload",
            "python -m twine upload",
            "gh release create",
            "git push --tags",
            "git tag",
            "git push --force",
            "git push --force-with-lease",
            "git reset --hard",
            "git clean",
            "git stash pop",
            "git stash drop",
            "git stash clear",
        ]
        for cmd in forbidden:
            assert cmd not in text, f"Found forbidden command: {cmd}"

    def test_contains_safety_checks(self) -> None:
        text = _script_path("local_quick_check.sh").read_text(encoding="utf-8")
        assert "check_forbidden_claims.py" in text
        assert "check_submit_execution_safety.py" in text
        assert "check_no_protected_staged.py" in text
        assert "git diff --check" in text

    def test_contains_demo_command_smoke_check(self) -> None:
        text = _script_path("local_quick_check.sh").read_text(encoding="utf-8")
        assert "check_demo_command_smoke.py" in text

    def test_contains_no_provider_or_broker_calls(self) -> None:
        text = _script_path("local_quick_check.sh").read_text(encoding="utf-8")
        assert "alpaca" not in text.lower()
        assert "binance" not in text.lower()
        assert "openai" not in text.lower()
        assert "anthropic" not in text.lower()

    def test_skips_historical_tests(self) -> None:
        text = _script_path("local_quick_check.sh").read_text(encoding="utf-8")
        # Should not include historical release checker test files
        assert "test_v058_" not in text
        assert "test_v060_" not in text
        assert "test_v061_" not in text
        assert "test_v062_" not in text
        assert "test_v063_" not in text
        assert "test_v064_" not in text
        assert "test_v065_" not in text
        assert "test_v066_" not in text

    def test_skips_slow_integration_tests(self) -> None:
        text = _script_path("local_quick_check.sh").read_text(encoding="utf-8")
        assert '-m "not slow"' in text
        assert "test_demo_research_workflow_script.py" not in text
        assert "test_package_distribution_check.py" not in text
        assert "test_clean_install_check.py" not in text
        assert "test_cli_ux_regression.py" not in text
        assert "test_reviewer_golden_path_smoke.py" not in text
        assert "test_research_provider_safety_dossier.py" not in text
        assert "test_research_sandbox_cli.py" not in text

    @pytest.mark.slow
    def test_runs_successfully(self, local_quick_check_result) -> None:
        result = local_quick_check_result
        assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert "All local quick checks passed" in result.stdout

    @pytest.mark.slow
    def test_respects_fail_fast_env(self) -> None:
        env = os.environ.copy()
        env["ATLAS_CHECK_FAIL_FAST"] = "1"
        env["ATLAS_CHECK_PYTEST_ARGS"] = "--collect-only"
        result = _run_shell(_script_path("local_quick_check.sh"), env=env)
        assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert "All local quick checks passed" in result.stdout

    @pytest.mark.slow
    def test_respects_last_failed_env(self) -> None:
        env = os.environ.copy()
        env["ATLAS_CHECK_LAST_FAILED"] = "1"
        env["ATLAS_CHECK_PYTEST_ARGS"] = "--collect-only"
        result = _run_shell(_script_path("local_quick_check.sh"), env=env)
        assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert "All local quick checks passed" in result.stdout

    def test_prints_reminder_about_full_gate(self, local_quick_check_result) -> None:
        result = local_quick_check_result
        assert "release_check.sh --full" in result.stdout

    def test_includes_core_unit_test_directories(self) -> None:
        text = _script_path("local_quick_check.sh").read_text(encoding="utf-8")
        assert "tests/agent/" in text
        assert "tests/audit/" in text
        assert "tests/backtest/" in text
        assert "tests/brokers/" in text
        assert "tests/cli/" in text
        assert "tests/config/" in text
        assert "tests/execution/" in text
        assert "tests/risk/" in text
        assert "tests/safety/" in text
