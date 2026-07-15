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


def _fake_python_environment(tmp_path: Path) -> tuple[dict[str, str], Path]:
    """Return an environment that records Python commands without rerunning tests.

    The checker scripts themselves have dedicated tests elsewhere in the suite.
    These wrapper tests only need to prove orchestration and argument forwarding,
    so launching the entire nested pytest subset would duplicate coverage.
    """
    log_path = tmp_path / "python-commands.log"
    fake_python = tmp_path / "fake-python"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'printf "%s\\n" "$*" >> "$FAKE_PYTHON_LOG"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    env = os.environ.copy()
    env["PYTHON_BIN"] = str(fake_python)
    env["FAKE_PYTHON_LOG"] = str(log_path)
    return env, log_path


@pytest.fixture(scope="module")
def smoke_check_result(tmp_path_factory: pytest.TempPathFactory) -> subprocess.CompletedProcess:
    env, _ = _fake_python_environment(tmp_path_factory.mktemp("smoke-check"))
    return _run_shell(_script_path("smoke_check.sh"), env=env)


@pytest.fixture(scope="module")
def local_quick_check_result(tmp_path_factory: pytest.TempPathFactory) -> subprocess.CompletedProcess:
    env, _ = _fake_python_environment(tmp_path_factory.mktemp("local-quick-check"))
    return _run_shell(_script_path("local_quick_check.sh"), env=env)


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
    def test_respects_fail_fast_env(self, tmp_path: Path) -> None:
        env, log_path = _fake_python_environment(tmp_path)
        env["ATLAS_CHECK_FAIL_FAST"] = "1"
        result = _run_shell(_script_path("smoke_check.sh"), env=env)
        assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert "All smoke checks passed" in result.stdout
        assert any(
            "-m pytest" in command and "-x" in command
            for command in log_path.read_text(encoding="utf-8").splitlines()
        )

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
        assert '-m "quick"' in text
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
    def test_respects_fail_fast_env(self, tmp_path: Path) -> None:
        env, log_path = _fake_python_environment(tmp_path)
        env["ATLAS_CHECK_FAIL_FAST"] = "1"
        result = _run_shell(_script_path("local_quick_check.sh"), env=env)
        assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert "All local quick checks passed" in result.stdout
        assert any(
            "-m pytest" in command and "-x" in command
            for command in log_path.read_text(encoding="utf-8").splitlines()
        )

    @pytest.mark.slow
    def test_respects_last_failed_env(self, tmp_path: Path) -> None:
        env, log_path = _fake_python_environment(tmp_path)
        env["ATLAS_CHECK_LAST_FAILED"] = "1"
        result = _run_shell(_script_path("local_quick_check.sh"), env=env)
        assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert "All local quick checks passed" in result.stdout
        assert any(
            "-m pytest" in command and "--lf" in command
            for command in log_path.read_text(encoding="utf-8").splitlines()
        )

    def test_prints_reminder_about_full_gate(self, local_quick_check_result) -> None:
        result = local_quick_check_result
        assert "release_check.sh --full" in result.stdout

    def test_automatically_collects_the_test_suite(self) -> None:
        text = _script_path("local_quick_check.sh").read_text(encoding="utf-8")
        assert '-m pytest tests -m "quick"' in text
        # A single collection root ensures newly added normal tests run without
        # requiring contributors to maintain a shell-script path allowlist.
        assert "tests/agent/" not in text
        assert "tests/research/test_research_cli.py" not in text
