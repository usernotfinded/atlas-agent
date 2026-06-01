"""Tests for scripts/smoke_package_build.sh.

These tests verify the package build smoke script using fake commands
so no real package building is required.
"""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest


SCRIPT_PATH = Path("scripts/smoke_package_build.sh")


def _write_fake_command(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def _make_fake_python3_11(
    bin_dir: Path,
    expected_version: str = "0.5.7.dev2",
    missing_wheel: bool = False,
    missing_sdist: bool = False,
    wrong_version: bool = False,
    build_deps_install_fail: bool = False,
) -> None:
    """Write a fake python3.11 that simulates pip/build/venv/package operations.

    When creating a venv, it also writes an ``atlas`` command into the venv
    that respects ``FAKE_ATLAS_HELP_FAIL`` and logs invocations to
    ``FAKE_ATLAS_INVOCATION_LOG``.

    Command logging to ``FAKE_PYTHON_COMMAND_LOG`` is supported for all
    invocations.
    """
    build_deps_fail_flag = "1" if build_deps_install_fail else "0"
    body = textwrap.dedent(
        f'''\
        set -euo pipefail
        # Log invocation if requested
        if [[ -n "${{FAKE_PYTHON_COMMAND_LOG:-}}" ]]; then
            printf '%s\\n' "$*" >> "$FAKE_PYTHON_COMMAND_LOG"
        fi
        # venv creation
        if [[ "$1" == "-m" && "$2" == "venv" ]]; then
            VENV="$3"
            mkdir -p "$VENV/bin"
            cat > "$VENV/bin/activate" <<'ACTEOF'
        # fake activate
        ACTEOF
            cp "$0" "$VENV/bin/python"
            chmod +x "$VENV/bin/python"
            # Create venv atlas that logs and respects FAKE_ATLAS_HELP_FAIL
            cat > "$VENV/bin/atlas" <<'ATLAS'
        #!/usr/bin/env bash
        set -euo pipefail
        if [[ -n "${{FAKE_ATLAS_INVOCATION_LOG:-}}" ]]; then
            printf 'venv-atlas:%s:%s\\n' "$0" "$*" >> "$FAKE_ATLAS_INVOCATION_LOG"
        fi
        if [[ "$1" == "--help" ]]; then
            if [[ "${{FAKE_ATLAS_HELP_FAIL:-0}}" == "1" ]]; then
                exit 1
            fi
            echo "Usage: atlas <command>"
            exit 0
        fi
        if [[ "$1" == "init" ]]; then
            mkdir -p "$2/.atlas"
            exit 0
        fi
        if [[ "$1" == "discipline" && "$2" == "setup" ]]; then
            exit 0
        fi
        if [[ "$1" == "config" && "$2" == "set" ]]; then
            exit 0
        fi
        if [[ "$1" == "validate" ]]; then
            exit 0
        fi
        if [[ "$1" == "run" ]]; then
            exit 0
        fi
        exit 0
        ATLAS
            chmod +x "$VENV/bin/atlas"
            exit 0
        fi
        # pip
        if [[ "$1" == "-m" && "$2" == "pip" ]]; then
            # Check for build dependency install failure
            if [[ "{build_deps_fail_flag}" == "1" ]]; then
                for arg in "$@"; do
                    if [[ "$arg" == "build" ]]; then
                        echo "Fake: build dependency install failed" >&2
                        exit 1
                    fi
                done
            fi
            for arg in "$@"; do
                if [[ "$arg" == "check" ]]; then
                    echo "No broken requirements found."
                    exit 0
                fi
            done
            exit 0
        fi
        # build --help check (offline mode validation)
        if [[ "$1" == "-m" && "$2" == "build" && "$3" == "--help" ]]; then
            echo "Usage: python -m build [options]"
            exit 0
        fi
        # build
        if [[ "$1" == "-m" && "$2" == "build" ]]; then
            OUTDIR=""
            while [[ $# -gt 0 ]]; do
                case "$1" in
                    --outdir) shift; OUTDIR="$1" ;;
                esac
                shift
            done
            mkdir -p "$OUTDIR"
            if [[ "{str(missing_wheel).lower()}" != "true" ]]; then
                touch "$OUTDIR/atlas_agent-{expected_version}-py3-none-any.whl"
            fi
            if [[ "{str(missing_sdist).lower()}" != "true" ]]; then
                touch "$OUTDIR/atlas_agent-{expected_version}.tar.gz"
            fi
            echo "Successfully built atlas_agent-{expected_version}.tar.gz and atlas_agent-{expected_version}-py3-none-any.whl"
            exit 0
        fi
        # package version check
        if [[ "$1" == "-c" ]]; then
            CODE="$2"
            if [[ "$CODE" == *"import atlas_agent"* ]]; then
                if [[ "{str(wrong_version).lower()}" == "true" ]]; then
                    echo "0.0.0.wrong"
                else
                    echo "{expected_version}"
                fi
                exit 0
            fi
            if [[ "$CODE" == *"tomllib"* ]]; then
                echo "{expected_version}"
                exit 0
            fi
            if [[ "$CODE" == *"sysconfig.get_path"* ]]; then
                echo "/fake/path"
                exit 0
            fi
        fi
        echo "Fake python3.11: unhandled args: $*" >&2
        exit 1
        '''
    )
    _write_fake_command(bin_dir, "python3.11", body)
    (bin_dir / "python").symlink_to("python3.11")


def _make_fake_build_python(
    bin_dir: Path,
    expected_version: str = "0.5.7.dev2",
    missing_wheel: bool = False,
    missing_sdist: bool = False,
    fail_help: bool = False,
) -> None:
    """Write a fake build python that only handles build commands."""
    fail_help_flag = "1" if fail_help else "0"
    body = textwrap.dedent(
        f'''\
        set -euo pipefail
        if [[ -n "${{FAKE_PYTHON_COMMAND_LOG:-}}" ]]; then
            printf '%s %s\\n' "$0" "$*" >> "$FAKE_PYTHON_COMMAND_LOG"
        fi
        if [[ "$1" == "-m" && "$2" == "build" && "$3" == "--help" ]]; then
            if [[ "{fail_help_flag}" == "1" ]]; then
                echo "Fake: build module not available" >&2
                exit 1
            fi
            echo "Usage: python -m build [options]"
            exit 0
        fi
        if [[ "$1" == "-m" && "$2" == "build" ]]; then
            OUTDIR=""
            while [[ $# -gt 0 ]]; do
                case "$1" in
                    --outdir) shift; OUTDIR="$1" ;;
                esac
                shift
            done
            mkdir -p "$OUTDIR"
            if [[ "{str(missing_wheel).lower()}" != "true" ]]; then
                touch "$OUTDIR/atlas_agent-{expected_version}-py3-none-any.whl"
            fi
            if [[ "{str(missing_sdist).lower()}" != "true" ]]; then
                touch "$OUTDIR/atlas_agent-{expected_version}.tar.gz"
            fi
            echo "Successfully built atlas_agent-{expected_version}.tar.gz and atlas_agent-{expected_version}-py3-none-any.whl"
            exit 0
        fi
        echo "Fake build python: unhandled args: $*" >&2
        exit 1
        '''
    )
    _write_fake_command(bin_dir, "build-python", body)


def _make_ambient_atlas(bin_dir: Path) -> None:
    """Ambient atlas that fails if called. Proves script uses venv atlas."""
    body = textwrap.dedent(
        '''\
        #!/usr/bin/env bash
        echo "ambient atlas was called" >&2
        exit 99
        '''
    )
    _write_fake_command(bin_dir, "atlas", body)


def _setup_env(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    env["ATLAS_KEEP_PACKAGE_SMOKE_DIR"] = "0"
    env.pop("ATLAS_PACKAGE_SMOKE_BUILD_PYTHON", None)
    return env, bin_dir


class TestSmokePackageBuildScript:
    def test_script_exists_and_is_executable(self) -> None:
        assert SCRIPT_PATH.exists(), f"{SCRIPT_PATH} does not exist"
        assert os.access(SCRIPT_PATH, os.X_OK), f"{SCRIPT_PATH} is not executable"

    def test_static_mutation_guard_no_repo_mutations(self) -> None:
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        forbidden = [
            "git add",
            "git commit",
            "git push",
            "git tag",
            "git reset",
            "git clean",
            "git restore",
            "git switch",
            "rm -rf .git",
            "twine upload",
        ]
        for cmd in forbidden:
            assert cmd not in content, f"Forbidden mutation command found: {cmd!r}"

    def test_no_manual_template_copy_workaround(self) -> None:
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "share/atlas-agent/templates" not in content
        assert "cp -r" not in content

    def test_build_uses_outdir_or_temp(self) -> None:
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "--outdir" in content, "Script must use --outdir to avoid polluting repo ./dist"
        assert 'build --outdir' in content

    def test_success_path_uses_installed_venv_atlas(self, tmp_path: Path) -> None:
        invocation_log = tmp_path / "atlas_invocations.log"
        env, bin_dir = _setup_env(tmp_path)
        _make_fake_python3_11(bin_dir)
        _make_ambient_atlas(bin_dir)
        env["FAKE_ATLAS_INVOCATION_LOG"] = str(invocation_log)

        result = subprocess.run(
            [str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path.cwd()),
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"Smoke failed:\n{combined}"
        assert "Package build smoke complete" in combined
        assert "ambient atlas was called" not in combined

        assert invocation_log.exists(), "Expected venv atlas invocation log to exist"
        log_text = invocation_log.read_text(encoding="utf-8")
        assert "venv-atlas:" in log_text, f"Expected venv-atlas marker in log: {log_text!r}"
        assert "--help" in log_text, f"Expected --help in log: {log_text!r}"
        assert "init" in log_text, f"Expected init in log: {log_text!r}"
        assert "validate" in log_text, f"Expected validate in log: {log_text!r}"
        assert "run" in log_text, f"Expected run in log: {log_text!r}"

    def test_installed_atlas_help_failure_fails_smoke(self, tmp_path: Path) -> None:
        invocation_log = tmp_path / "atlas_invocations.log"
        env, bin_dir = _setup_env(tmp_path)
        _make_fake_python3_11(bin_dir)
        _make_ambient_atlas(bin_dir)
        env["FAKE_ATLAS_INVOCATION_LOG"] = str(invocation_log)
        env["FAKE_ATLAS_HELP_FAIL"] = "1"

        result = subprocess.run(
            [str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path.cwd()),
        )
        combined = result.stdout + result.stderr
        assert result.returncode != 0, f"Expected failure for atlas --help failure:\n{combined}"
        assert "Installed atlas CLI help failed." in combined

        assert invocation_log.exists(), "Expected venv atlas invocation log to exist"
        log_text = invocation_log.read_text(encoding="utf-8")
        assert "--help" in log_text, f"Expected --help in log: {log_text!r}"

    def test_wheel_missing_fails(self, tmp_path: Path) -> None:
        env, bin_dir = _setup_env(tmp_path)
        _make_fake_python3_11(bin_dir, missing_wheel=True)
        _make_ambient_atlas(bin_dir)

        result = subprocess.run(
            [str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path.cwd()),
        )
        combined = result.stdout + result.stderr
        assert result.returncode != 0, f"Expected failure for missing wheel:\n{combined}"
        assert "no wheel found" in combined.lower() or "wheel" in combined.lower()

    def test_sdist_missing_fails_by_default(self, tmp_path: Path) -> None:
        env, bin_dir = _setup_env(tmp_path)
        _make_fake_python3_11(bin_dir, missing_sdist=True)
        _make_ambient_atlas(bin_dir)

        result = subprocess.run(
            [str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path.cwd()),
        )
        combined = result.stdout + result.stderr
        assert result.returncode != 0, f"Expected failure for missing sdist:\n{combined}"
        assert "no sdist found" in combined.lower() or "sdist" in combined.lower()

    def test_skip_sdist_allows_missing_sdist(self, tmp_path: Path) -> None:
        env, bin_dir = _setup_env(tmp_path)
        _make_fake_python3_11(bin_dir, missing_sdist=True)
        _make_ambient_atlas(bin_dir)

        result = subprocess.run(
            [str(SCRIPT_PATH), "--skip-sdist"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path.cwd()),
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"Smoke failed:\n{combined}"
        assert "sdist check skipped" in combined.lower()

    def test_installed_version_mismatch_fails(self, tmp_path: Path) -> None:
        env, bin_dir = _setup_env(tmp_path)
        _make_fake_python3_11(bin_dir, wrong_version=True)
        _make_ambient_atlas(bin_dir)

        result = subprocess.run(
            [str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path.cwd()),
        )
        combined = result.stdout + result.stderr
        assert result.returncode != 0, f"Expected failure for version mismatch:\n{combined}"
        assert "does not match expected" in combined.lower() or "version" in combined.lower()

    def test_keep_artifacts_prevents_cleanup(self, tmp_path: Path) -> None:
        env, bin_dir = _setup_env(tmp_path)
        _make_fake_python3_11(bin_dir)
        _make_ambient_atlas(bin_dir)

        result = subprocess.run(
            [str(SCRIPT_PATH), "--keep-artifacts"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path.cwd()),
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"Smoke failed:\n{combined}"
        assert "Artifacts kept" in combined

    # ------------------------------------------------------------------
    # Offline mode tests
    # ------------------------------------------------------------------

    def test_offline_skips_build_dependency_installation(self, tmp_path: Path) -> None:
        command_log = tmp_path / "python_commands.log"
        invocation_log = tmp_path / "atlas_invocations.log"
        env, bin_dir = _setup_env(tmp_path)
        _make_fake_python3_11(bin_dir)
        _make_ambient_atlas(bin_dir)
        env["FAKE_PYTHON_COMMAND_LOG"] = str(command_log)
        env["FAKE_ATLAS_INVOCATION_LOG"] = str(invocation_log)

        result = subprocess.run(
            [str(SCRIPT_PATH), "--offline"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path.cwd()),
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"Smoke failed:\n{combined}"
        assert "Package build smoke complete" in combined

        assert command_log.exists(), "Expected command log to exist"
        log_text = command_log.read_text(encoding="utf-8")
        assert "-m pip install --quiet --upgrade pip build" not in log_text, (
            f"Offline mode should not install build deps: {log_text!r}"
        )
        assert "-m pip install build" not in log_text, (
            f"Offline mode should not install build deps: {log_text!r}"
        )
        # Still builds and installs wheel
        assert "build --outdir" in log_text, f"Expected build command in log: {log_text!r}"

    def test_skip_build_deps_install_alias_like_offline(self, tmp_path: Path) -> None:
        command_log = tmp_path / "python_commands.log"
        invocation_log = tmp_path / "atlas_invocations.log"
        env, bin_dir = _setup_env(tmp_path)
        _make_fake_python3_11(bin_dir)
        _make_ambient_atlas(bin_dir)
        env["FAKE_PYTHON_COMMAND_LOG"] = str(command_log)
        env["FAKE_ATLAS_INVOCATION_LOG"] = str(invocation_log)

        result = subprocess.run(
            [str(SCRIPT_PATH), "--skip-build-deps-install"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path.cwd()),
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"Smoke failed:\n{combined}"
        assert "Package build smoke complete" in combined

        assert command_log.exists(), "Expected command log to exist"
        log_text = command_log.read_text(encoding="utf-8")
        assert "-m pip install --quiet --upgrade pip build" not in log_text, (
            f"Alias should skip build deps install: {log_text!r}"
        )

    def test_offline_fails_when_build_unavailable(self, tmp_path: Path) -> None:
        env, bin_dir = _setup_env(tmp_path)
        _make_fake_build_python(bin_dir, fail_help=True)
        _make_ambient_atlas(bin_dir)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["ATLAS_KEEP_PACKAGE_SMOKE_DIR"] = "0"
        env.pop("ATLAS_PACKAGE_SMOKE_BUILD_PYTHON", None)
        env["ATLAS_PACKAGE_SMOKE_BUILD_PYTHON"] = str(bin_dir / "build-python")

        result = subprocess.run(
            [str(SCRIPT_PATH), "--offline"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path.cwd()),
        )
        combined = result.stdout + result.stderr
        assert result.returncode != 0, f"Expected failure when build missing:\n{combined}"
        assert (
            "Offline package smoke requires the 'build' package to be installed for the selected build Python."
            in combined
        )
        assert "Traceback" not in combined

    def test_default_mode_attempts_build_dependency_installation(self, tmp_path: Path) -> None:
        command_log = tmp_path / "python_commands.log"
        env, bin_dir = _setup_env(tmp_path)
        _make_fake_python3_11(bin_dir)
        _make_ambient_atlas(bin_dir)
        env["FAKE_PYTHON_COMMAND_LOG"] = str(command_log)

        result = subprocess.run(
            [str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path.cwd()),
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"Smoke failed:\n{combined}"

        assert command_log.exists(), "Expected command log to exist"
        log_text = command_log.read_text(encoding="utf-8")
        assert "-m pip install --quiet --upgrade pip build" in log_text, (
            f"Default mode should install build deps: {log_text!r}"
        )

    def test_online_dependency_install_failure_gives_offline_hint(self, tmp_path: Path) -> None:
        env, bin_dir = _setup_env(tmp_path)
        _make_fake_python3_11(bin_dir, build_deps_install_fail=True)
        _make_ambient_atlas(bin_dir)

        result = subprocess.run(
            [str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path.cwd()),
        )
        combined = result.stdout + result.stderr
        assert result.returncode != 0, f"Expected failure for dep install failure:\n{combined}"
        assert "rerun with --offline" in combined
        assert "Package build smoke complete" not in combined

    def test_offline_does_not_upgrade_pip_in_install_venv(self, tmp_path: Path) -> None:
        command_log = tmp_path / "python_commands.log"
        env, bin_dir = _setup_env(tmp_path)
        _make_fake_python3_11(bin_dir)
        _make_ambient_atlas(bin_dir)
        env["FAKE_PYTHON_COMMAND_LOG"] = str(command_log)

        result = subprocess.run(
            [str(SCRIPT_PATH), "--offline"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path.cwd()),
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"Smoke failed:\n{combined}"

        assert command_log.exists(), "Expected command log to exist"
        log_text = command_log.read_text(encoding="utf-8")
        assert "-m pip install --quiet --upgrade pip" not in log_text, (
            f"Offline mode should not upgrade pip in install venv: {log_text!r}"
        )
        # Local wheel install is still allowed
        assert "-m pip install --quiet" in log_text, (
            f"Offline mode should still install local wheel: {log_text!r}"
        )

    def test_offline_uses_existing_selected_build_python(self, tmp_path: Path) -> None:
        command_log = tmp_path / "python_commands.log"
        invocation_log = tmp_path / "atlas_invocations.log"
        env, bin_dir = _setup_env(tmp_path)
        _make_fake_python3_11(bin_dir)
        _make_fake_build_python(bin_dir)
        _make_ambient_atlas(bin_dir)
        env["FAKE_PYTHON_COMMAND_LOG"] = str(command_log)
        env["FAKE_ATLAS_INVOCATION_LOG"] = str(invocation_log)
        env["ATLAS_PACKAGE_SMOKE_BUILD_PYTHON"] = str(bin_dir / "build-python")

        result = subprocess.run(
            [str(SCRIPT_PATH), "--offline"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path.cwd()),
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"Smoke failed:\n{combined}"
        assert "Package build smoke complete" in combined

        assert command_log.exists(), "Expected command log to exist"
        log_text = command_log.read_text(encoding="utf-8")
        # Build python was used for build commands
        assert "build-python -m build --help" in log_text, (
            f"Expected build-python --help in log: {log_text!r}"
        )
        assert "build-python -m build --outdir" in log_text, (
            f"Expected build-python build in log: {log_text!r}"
        )
        # No build venv was created in offline mode
        assert "-m venv" not in log_text or "build-venv" not in log_text, (
            f"Offline mode should not create build venv: {log_text!r}"
        )

    def test_offline_passes_with_selected_build_python(self, tmp_path: Path) -> None:
        command_log = tmp_path / "python_commands.log"
        invocation_log = tmp_path / "atlas_invocations.log"
        env, bin_dir = _setup_env(tmp_path)
        _make_fake_python3_11(bin_dir)
        _make_fake_build_python(bin_dir)
        _make_ambient_atlas(bin_dir)
        env["FAKE_PYTHON_COMMAND_LOG"] = str(command_log)
        env["FAKE_ATLAS_INVOCATION_LOG"] = str(invocation_log)
        env["ATLAS_PACKAGE_SMOKE_BUILD_PYTHON"] = str(bin_dir / "build-python")

        result = subprocess.run(
            [str(SCRIPT_PATH), "--offline"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path.cwd()),
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"Smoke failed:\n{combined}"
        assert "Package build smoke complete" in combined
        assert "ambient atlas was called" not in combined

        assert invocation_log.exists(), "Expected venv atlas invocation log to exist"
        log_text = invocation_log.read_text(encoding="utf-8")
        assert "venv-atlas:" in log_text, f"Expected venv-atlas marker in log: {log_text!r}"
        assert "--help" in log_text, f"Expected --help in log: {log_text!r}"
