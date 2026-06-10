"""Tests for release-check scripts."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


def _run_script(script_name: str, *args: str, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    repo_root = Path(__file__).resolve().parent.parent
    script_path = repo_root / "scripts" / script_name
    result = subprocess.run(
        [sys.executable, str(script_path), *args],
        capture_output=True,
        text=True,
        cwd=cwd or repo_root,
        env=env,
    )
    return result


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


def _write_fake_python(path: Path, marker_name: str, *, validate_exit: int = 0, validate_message: str = "") -> None:
    path.write_text(
        '#!/usr/bin/env bash\n'
        'set -euo pipefail\n'
        'if [[ "${1:-}" == "-" ]]; then\n'
        f'    touch "$MARKER_DIR/{marker_name}"\n'
        '    cat >/dev/null\n'
        f'    if [[ "{validate_message}" != "" ]]; then\n'
        f'        printf "%s\\n" "{validate_message}" >&2\n'
        '    fi\n'
        f'    exit "{validate_exit}"\n'
        'fi\n'
        'exit 0\n',
        encoding="utf-8",
    )
    path.chmod(0o755)


# ---------------------------------------------------------------------------
# python_env.sh
# ---------------------------------------------------------------------------

class TestPythonEnvSh:
    def _run_helper(self, tmp_path: Path, env: dict) -> subprocess.CompletedProcess:
        repo_root = Path(__file__).resolve().parent.parent
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        helper = scripts_dir / "python_env.sh"
        helper.write_text(
            (repo_root / "scripts" / "python_env.sh").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        return subprocess.run(
            [
                "/bin/bash",
                "-c",
                'source scripts/python_env.sh; resolved="$(resolve_python_bin)"; '
                'printf "resolved=%s\\n" "$resolved"; require_python_311 "$resolved"',
            ],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env=env,
        )

    def test_explicit_python_bin_override_is_respected(self, tmp_path: Path) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        marker_dir = tmp_path / "markers"
        marker_dir.mkdir()
        custom_python = bin_dir / "custom-python"
        _write_fake_python(custom_python, "custom.marker")
        _write_fake_python(bin_dir / "python3.11", "python311.marker")

        env = os.environ.copy()
        env["MARKER_DIR"] = str(marker_dir)
        env["PATH"] = f"{bin_dir}:/bin:/usr/bin"
        env["PYTHON_BIN"] = str(custom_python)

        result = self._run_helper(tmp_path, env)

        assert result.returncode == 0
        assert f"resolved={custom_python}" in result.stdout
        assert (marker_dir / "custom.marker").exists()
        assert not (marker_dir / "python311.marker").exists()

    def test_default_prefers_python311_when_available(self, tmp_path: Path) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        marker_dir = tmp_path / "markers"
        marker_dir.mkdir()
        _write_fake_python(bin_dir / "python3.11", "python311.marker")
        _write_fake_python(bin_dir / "python", "python.marker")

        env = os.environ.copy()
        env["MARKER_DIR"] = str(marker_dir)
        env["PATH"] = f"{bin_dir}:/bin:/usr/bin"
        env.pop("PYTHON_BIN", None)

        result = self._run_helper(tmp_path, env)

        assert result.returncode == 0
        assert "resolved=python3.11" in result.stdout
        assert (marker_dir / "python311.marker").exists()
        assert not (marker_dir / "python.marker").exists()

    def test_default_falls_back_to_python_when_python311_missing(self, tmp_path: Path) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        marker_dir = tmp_path / "markers"
        marker_dir.mkdir()
        _write_fake_python(bin_dir / "python", "python.marker")

        env = os.environ.copy()
        env["MARKER_DIR"] = str(marker_dir)
        env["PATH"] = f"{bin_dir}:/bin:/usr/bin"
        env.pop("PYTHON_BIN", None)

        result = self._run_helper(tmp_path, env)

        assert result.returncode == 0
        assert "resolved=python" in result.stdout
        assert (marker_dir / "python.marker").exists()

    def test_python_version_failure_is_clear(self, tmp_path: Path) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        marker_dir = tmp_path / "markers"
        marker_dir.mkdir()
        _write_fake_python(
            bin_dir / "python3.11",
            "python311.marker",
            validate_exit=1,
            validate_message="Python >= 3.11 required, got 3.10.0",
        )

        env = os.environ.copy()
        env["MARKER_DIR"] = str(marker_dir)
        env["PATH"] = f"{bin_dir}:/bin:/usr/bin"
        env.pop("PYTHON_BIN", None)

        result = self._run_helper(tmp_path, env)

        assert result.returncode != 0
        assert "Python >= 3.11 required, got 3.10.0" in result.stderr
        assert (marker_dir / "python311.marker").exists()


# ---------------------------------------------------------------------------
# check_version_consistency.py
# ---------------------------------------------------------------------------

class TestCheckVersionConsistency:
    def test_match(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")
        init_dir = tmp_path / "src" / "atlas_agent"
        init_dir.mkdir(parents=True)
        init_file = init_dir / "__init__.py"
        init_file.write_text('__version__ = "1.2.3"\n', encoding="utf-8")
        meta_dir = tmp_path / "docs" / "releases"
        meta_dir.mkdir(parents=True, exist_ok=True)
        meta_file = meta_dir / "release-metadata.json"
        meta_file.write_text("""{"source_version": "1.2.3", "current_public_release": "v1.2.2"}""", encoding="utf-8")
        (meta_dir / "v1.2.2.md").touch()



        result = _run_script("check_version_consistency.py", str(tmp_path))
        assert result.returncode == 0
        assert "1.2.3" in result.stdout

    def test_mismatch(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")
        init_dir = tmp_path / "src" / "atlas_agent"
        init_dir.mkdir(parents=True)
        init_file = init_dir / "__init__.py"
        init_file.write_text('__version__ = "1.2.4"\n', encoding="utf-8")
        meta_dir = tmp_path / "docs" / "releases"
        meta_dir.mkdir(parents=True, exist_ok=True)
        meta_file = meta_dir / "release-metadata.json"
        meta_file.write_text("""{"source_version": "1.2.3", "current_public_release": "v1.2.2"}""", encoding="utf-8")
        (meta_dir / "v1.2.2.md").touch()



        result = _run_script("check_version_consistency.py", str(tmp_path))
        assert result.returncode == 2
        assert "mismatch" in result.stdout.lower() or "failed" in result.stdout.lower()

    def test_missing_pyproject(self, tmp_path: Path) -> None:
        init_dir = tmp_path / "src" / "atlas_agent"
        init_dir.mkdir(parents=True)
        init_file = init_dir / "__init__.py"
        init_file.write_text('__version__ = "1.0.0"\n', encoding="utf-8")
        meta_dir = tmp_path / "docs" / "releases"
        meta_dir.mkdir(parents=True, exist_ok=True)
        meta_file = meta_dir / "release-metadata.json"
        meta_file.write_text("""{"source_version": "1.2.3", "current_public_release": "v1.2.2"}""", encoding="utf-8")
        (meta_dir / "v1.2.2.md").touch()



        result = _run_script("check_version_consistency.py", str(tmp_path))
        assert result.returncode == 2

    def test_missing_init(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nversion = "1.0.0"\n', encoding="utf-8")

        result = _run_script("check_version_consistency.py", str(tmp_path))
        assert result.returncode == 2


# ---------------------------------------------------------------------------
# check_forbidden_claims.py
# ---------------------------------------------------------------------------

class TestCheckForbiddenClaims:
    def test_detects_guaranteed_profit(self, tmp_path: Path) -> None:
        readme = tmp_path / "README.md"
        readme.write_text("This strategy offers guaranteed profit!\n", encoding="utf-8")

        result = _run_script("check_forbidden_claims.py", str(tmp_path))
        assert result.returncode == 2
        assert "guaranteed profit" in result.stdout

    def test_detects_safe_live_trading(self, tmp_path: Path) -> None:
        readme = tmp_path / "README.md"
        readme.write_text("Enjoy safe live trading with our bot.\n", encoding="utf-8")

        result = _run_script("check_forbidden_claims.py", str(tmp_path))
        assert result.returncode == 2
        assert "safe live trading" in result.stdout

    def test_detects_zero_risk_hyphenated(self, tmp_path: Path) -> None:
        readme = tmp_path / "README.md"
        readme.write_text("This is a zero-risk investment.\n", encoding="utf-8")

        result = _run_script("check_forbidden_claims.py", str(tmp_path))
        assert result.returncode == 2
        assert "zero risk" in result.stdout

    def test_detects_guaranteed_profit_uppercase(self, tmp_path: Path) -> None:
        readme = tmp_path / "README.md"
        readme.write_text("GUARANTEED PROFIT for everyone!\n", encoding="utf-8")

        result = _run_script("check_forbidden_claims.py", str(tmp_path))
        assert result.returncode == 2
        assert "guaranteed profit" in result.stdout

    def test_detects_safe_live_trading_mixed_case(self, tmp_path: Path) -> None:
        readme = tmp_path / "README.md"
        readme.write_text("Our bot enables Safe Live Trading.\n", encoding="utf-8")

        result = _run_script("check_forbidden_claims.py", str(tmp_path))
        assert result.returncode == 2
        assert "safe live trading" in result.stdout

    def test_detects_unattended_live_trading_uppercase(self, tmp_path: Path) -> None:
        readme = tmp_path / "README.md"
        readme.write_text("UNATTENDED LIVE TRADING is supported.\n", encoding="utf-8")

        result = _run_script("check_forbidden_claims.py", str(tmp_path))
        assert result.returncode == 2
        assert "unattended live trading" in result.stdout

    def test_detects_guaranteed_returns(self, tmp_path: Path) -> None:
        readme = tmp_path / "README.md"
        readme.write_text("We promise guaranteed returns.\n", encoding="utf-8")

        result = _run_script("check_forbidden_claims.py", str(tmp_path))
        assert result.returncode == 2
        assert "guaranteed returns" in result.stdout

    def test_clean(self, tmp_path: Path) -> None:
        readme = tmp_path / "README.md"
        readme.write_text(
            "Atlas Agent is a broker-neutral supervised trading workspace.\n"
            "Live trading is disabled by default.\n",
            encoding="utf-8",
        )

        result = _run_script("check_forbidden_claims.py", str(tmp_path))
        assert result.returncode == 0
        assert "clean" in result.stdout.lower()

    def test_no_false_positive_on_meta_safety(self, tmp_path: Path) -> None:
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(
            "- No prohibited trading-safety or profit-promise claims added.\n",
            encoding="utf-8",
        )

        result = _run_script("check_forbidden_claims.py", str(tmp_path))
        assert result.returncode == 0
        assert "clean" in result.stdout.lower()

    def test_no_false_positive_on_exposure_wording(self, tmp_path: Path) -> None:
        docs = tmp_path / "docs"
        docs.mkdir()
        plan = docs / "plan.md"
        plan.write_text(
            "- Default configuration is designed to block accidental live submit paths.\n"
            "- No sync, no exposure, no can_submit check reached.\n",
            encoding="utf-8",
        )

        result = _run_script("check_forbidden_claims.py", str(tmp_path))
        assert result.returncode == 0

    def test_skips_binary_files(self, tmp_path: Path) -> None:
        readme = tmp_path / "README.md"
        readme.write_text("Clean text.\n", encoding="utf-8")
        binary = tmp_path / "image.png"
        binary.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

        result = _run_script("check_forbidden_claims.py", str(tmp_path))
        assert result.returncode == 0

    def test_ignores_missing_optional_paths(self, tmp_path: Path) -> None:
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text("Clean changelog.\n", encoding="utf-8")
        # README.md and docs/ and .github/ are intentionally missing

        result = _run_script("check_forbidden_claims.py", str(tmp_path))
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# release_check.sh
# ---------------------------------------------------------------------------

class TestReleaseCheckSh:
    def test_exists_and_is_executable(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        script = repo_root / "scripts" / "release_check.sh"
        assert script.exists()
        assert script.stat().st_mode & 0o111, "release_check.sh should be executable"

    def _setup_fake_repo(self, tmp_path: Path) -> Path:
        """Create a fake repo with intercepting executables and marker support."""
        repo_root = Path(__file__).resolve().parent.parent
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        marker_dir = tmp_path / "markers"
        marker_dir.mkdir()

        # Copy real release_check.sh
        real_release = repo_root / "scripts" / "release_check.sh"
        fake_release = scripts_dir / "release_check.sh"
        fake_release.write_text(real_release.read_text(encoding="utf-8"), encoding="utf-8")
        fake_release.chmod(0o755)
        fake_helper = scripts_dir / "python_env.sh"
        fake_helper.write_text(
            (repo_root / "scripts" / "python_env.sh").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        # Fake python3.11 dispatcher
        fake_python = bin_dir / "python3.11"
        fake_python.write_text(
            '#!/usr/bin/env bash\n'
            'set -euo pipefail\n'
            'MARKER_DIR="' + str(marker_dir) + '"\n'
            'if [[ "$1" == "-m" && "$2" == "pytest" ]]; then\n'
            '    touch "$MARKER_DIR/pytest.marker"\n'
            '    exit "${PYTEST_EXIT:-0}"\n'
            'elif [[ "$1" == "-m" && "$2" == "pip" && "$3" == "check" ]]; then\n'
            '    touch "$MARKER_DIR/pip_check.marker"\n'
            '    exit "${PIP_CHECK_EXIT:-0}"\n'
            'elif [[ "$1" == "scripts/check_version_consistency.py" ]]; then\n'
            '    touch "$MARKER_DIR/version.marker"\n'
            '    exit "${VERSION_EXIT:-0}"\n'
            'elif [[ "$1" == "scripts/check_forbidden_claims.py" ]]; then\n'
            '    touch "$MARKER_DIR/claims.marker"\n'
            '    exit "${CLAIMS_EXIT:-0}"\n'
            'fi\n'
            'exit 0\n',
            encoding="utf-8",
        )
        fake_python.chmod(0o755)

        # Also provide 'python' symlink so fallback behavior is covered.
        (bin_dir / "python").symlink_to(fake_python)

        # Fake git
        fake_git = bin_dir / "git"
        fake_git.write_text(
            '#!/usr/bin/env bash\n'
            'set -euo pipefail\n'
            'MARKER_DIR="' + str(marker_dir) + '"\n'
            'if [[ "${1:-}" == "diff" && "${2:-}" == "--cached" && "${3:-}" == "--check" ]]; then\n'
            '    touch "$MARKER_DIR/git_diff_cached.marker"\n'
            '    exit "${GIT_DIFF_CACHED_EXIT:-${GIT_DIFF_EXIT:-0}}"\n'
            'elif [[ "${1:-}" == "diff" && "${2:-}" == "--check" ]]; then\n'
            '    touch "$MARKER_DIR/git_diff.marker"\n'
            '    exit "${GIT_DIFF_EXIT:-0}"\n'
            'fi\n'
            'exit 0\n',
            encoding="utf-8",
        )
        fake_git.chmod(0o755)

        # Fake demo_paper_workflow.sh
        fake_demo = scripts_dir / "demo_paper_workflow.sh"
        fake_demo.write_text(
            '#!/usr/bin/env bash\n'
            'set -euo pipefail\n'
            'MARKER_DIR="' + str(marker_dir) + '"\n'
            'touch "$MARKER_DIR/demo.marker"\n'
            'exit "${DEMO_EXIT:-0}"\n',
            encoding="utf-8",
        )
        fake_demo.chmod(0o755)

        # Fake demo_research_workflow.sh
        fake_demo_research = scripts_dir / "demo_research_workflow.sh"
        fake_demo_research.write_text(
            '#!/usr/bin/env bash\n'
            'set -euo pipefail\n'
            'MARKER_DIR="' + str(marker_dir) + '"\n'
            'touch "$MARKER_DIR/demo_research.marker"\n'
            'exit "${DEMO_RESEARCH_EXIT:-0}"\n',
            encoding="utf-8",
        )
        fake_demo_research.chmod(0o755)

        # Fake dev_check.sh
        fake_dev = scripts_dir / "dev_check.sh"
        fake_dev.write_text(
            '#!/usr/bin/env bash\n'
            'set -euo pipefail\n'
            'MARKER_DIR="' + str(marker_dir) + '"\n'
            'touch "$MARKER_DIR/dev_check.marker"\n'
            'exit "${DEV_CHECK_EXIT:-0}"\n',
            encoding="utf-8",
        )
        fake_dev.chmod(0o755)

        # Fake research_check.sh
        fake_research = scripts_dir / "research_check.sh"
        fake_research.write_text(
            '#!/usr/bin/env bash\n'
            'set -euo pipefail\n'
            'MARKER_DIR="' + str(marker_dir) + '"\n'
            'touch "$MARKER_DIR/research_check.marker"\n'
            'exit "${RESEARCH_CHECK_EXIT:-0}"\n',
            encoding="utf-8",
        )
        fake_research.chmod(0o755)

        # Stub pyproject.toml and __init__.py so version check passes when called
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nversion = "0.0.0"\n', encoding="utf-8")
        init_dir = tmp_path / "src" / "atlas_agent"
        init_dir.mkdir(parents=True)
        init_file = init_dir / "__init__.py"
        init_file.write_text('__version__ = "0.0.0"\n', encoding="utf-8")
        meta_dir = tmp_path / "docs" / "releases"
        meta_dir.mkdir(parents=True, exist_ok=True)
        meta_file = meta_dir / "release-metadata.json"
        meta_file.write_text("""{"source_version": "1.2.3", "current_public_release": "v1.2.2"}""", encoding="utf-8")
        (meta_dir / "v1.2.2.md").touch()



        return marker_dir

    def test_fail_fast_on_pytest_failure(self, tmp_path: Path) -> None:
        marker_dir = self._setup_fake_repo(tmp_path)
        env = os.environ.copy()
        env["PATH"] = f"{tmp_path / 'bin'}:{env.get('PATH', '')}"
        env["PYTEST_EXIT"] = "1"
        env["PIP_CHECK_EXIT"] = "0"
        env["DEMO_EXIT"] = "0"
        env["GIT_DIFF_EXIT"] = "0"
        env["VERSION_EXIT"] = "0"
        env["CLAIMS_EXIT"] = "0"

        result = _run_shell(tmp_path / "scripts" / "release_check.sh", cwd=tmp_path, env=env)

        assert result.returncode != 0
        assert (marker_dir / "pytest.marker").exists()
        assert not (marker_dir / "pip_check.marker").exists()
        assert not (marker_dir / "demo.marker").exists()
        assert not (marker_dir / "git_diff.marker").exists()
        assert not (marker_dir / "version.marker").exists()
        assert not (marker_dir / "claims.marker").exists()
        assert "All release checks passed" not in result.stdout
        assert "All release checks passed" not in result.stderr

    def test_fail_fast_on_demo_failure(self, tmp_path: Path) -> None:
        marker_dir = self._setup_fake_repo(tmp_path)
        env = os.environ.copy()
        env["PATH"] = f"{tmp_path / 'bin'}:{env.get('PATH', '')}"
        env["PYTEST_EXIT"] = "0"
        env["PIP_CHECK_EXIT"] = "0"
        env["DEMO_EXIT"] = "1"
        env["GIT_DIFF_EXIT"] = "0"
        env["VERSION_EXIT"] = "0"
        env["CLAIMS_EXIT"] = "0"

        result = _run_shell(tmp_path / "scripts" / "release_check.sh", cwd=tmp_path, env=env)

        assert result.returncode != 0
        assert (marker_dir / "pytest.marker").exists()
        assert (marker_dir / "pip_check.marker").exists()
        assert (marker_dir / "demo.marker").exists()
        assert not (marker_dir / "git_diff.marker").exists()
        assert not (marker_dir / "version.marker").exists()
        assert not (marker_dir / "claims.marker").exists()
        assert "All release checks passed" not in result.stdout
        assert "All release checks passed" not in result.stderr

    def test_fail_fast_on_git_diff_failure(self, tmp_path: Path) -> None:
        marker_dir = self._setup_fake_repo(tmp_path)
        env = os.environ.copy()
        env["PATH"] = f"{tmp_path / 'bin'}:{env.get('PATH', '')}"
        env["PYTEST_EXIT"] = "0"
        env["PIP_CHECK_EXIT"] = "0"
        env["DEMO_EXIT"] = "0"
        env["GIT_DIFF_EXIT"] = "1"
        env["VERSION_EXIT"] = "0"
        env["CLAIMS_EXIT"] = "0"

        result = _run_shell(tmp_path / "scripts" / "release_check.sh", cwd=tmp_path, env=env)

        assert result.returncode != 0
        assert (marker_dir / "pytest.marker").exists()
        assert (marker_dir / "pip_check.marker").exists()
        assert (marker_dir / "demo.marker").exists()
        assert (marker_dir / "git_diff.marker").exists()
        assert not (marker_dir / "git_diff_cached.marker").exists()
        assert not (marker_dir / "version.marker").exists()
        assert not (marker_dir / "claims.marker").exists()
        assert "All release checks passed" not in result.stdout
        assert "All release checks passed" not in result.stderr

    def test_fail_fast_on_git_diff_cached_failure(self, tmp_path: Path) -> None:
        marker_dir = self._setup_fake_repo(tmp_path)
        env = os.environ.copy()
        env["PATH"] = f"{tmp_path / 'bin'}:{env.get('PATH', '')}"
        env["PYTEST_EXIT"] = "0"
        env["PIP_CHECK_EXIT"] = "0"
        env["DEMO_EXIT"] = "0"
        env["GIT_DIFF_EXIT"] = "0"
        env["GIT_DIFF_CACHED_EXIT"] = "1"
        env["VERSION_EXIT"] = "0"
        env["CLAIMS_EXIT"] = "0"

        result = _run_shell(tmp_path / "scripts" / "release_check.sh", cwd=tmp_path, env=env)

        assert result.returncode != 0
        assert (marker_dir / "pytest.marker").exists()
        assert (marker_dir / "pip_check.marker").exists()
        assert (marker_dir / "demo.marker").exists()
        assert (marker_dir / "git_diff.marker").exists()
        assert (marker_dir / "git_diff_cached.marker").exists()
        assert not (marker_dir / "version.marker").exists()
        assert not (marker_dir / "claims.marker").exists()
        assert "All release checks passed" not in result.stdout
        assert "All release checks passed" not in result.stderr

    def test_success_all_checks_pass(self, tmp_path: Path) -> None:
        marker_dir = self._setup_fake_repo(tmp_path)
        env = os.environ.copy()
        env["PATH"] = f"{tmp_path / 'bin'}:{env.get('PATH', '')}"
        env["PYTEST_EXIT"] = "0"
        env["PIP_CHECK_EXIT"] = "0"
        env["DEMO_EXIT"] = "0"
        env["GIT_DIFF_EXIT"] = "0"
        env["VERSION_EXIT"] = "0"
        env["CLAIMS_EXIT"] = "0"

        result = _run_shell(tmp_path / "scripts" / "release_check.sh", cwd=tmp_path, env=env)

        assert result.returncode == 0
        assert (marker_dir / "pytest.marker").exists()
        assert (marker_dir / "pip_check.marker").exists()
        assert (marker_dir / "demo.marker").exists()
        assert (marker_dir / "git_diff.marker").exists()
        assert (marker_dir / "git_diff_cached.marker").exists()
        assert (marker_dir / "version.marker").exists()
        assert (marker_dir / "claims.marker").exists()
        assert "All release checks passed" in result.stdout

    def test_static_mutation_guard(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        script_path = repo_root / "scripts" / "release_check.sh"
        content = script_path.read_text(encoding="utf-8")

        forbidden_patterns = [
            "git add",
            "git commit",
            "git push",
            "git checkout",
            "git reset",
            "git clean",
            "git restore",
            "git switch",
            "gh release",
            "rm -rf .git",
            "sed -i",
            "perl -pi",
            "tee -a",
        ]

        for pattern in forbidden_patterns:
            assert pattern not in content, (
                f"release_check.sh contains forbidden mutation pattern: {pattern}"
            )

        # Verify the intended git diff --check is still present
        assert "git diff --check" in content


    def test_quick_runs_dev_check(self, tmp_path: Path) -> None:
        marker_dir = self._setup_fake_repo(tmp_path)
        env = os.environ.copy()
        env["PATH"] = f"{tmp_path / 'bin'}:{env.get('PATH', '')}"
        env["DEV_CHECK_EXIT"] = "0"

        result = _run_shell(
            tmp_path / "scripts" / "release_check.sh",
            cwd=tmp_path,
            env=env,
            args=["--quick"],
        )

        assert result.returncode == 0
        assert (marker_dir / "dev_check.marker").exists()
        assert not (marker_dir / "pytest.marker").exists()
        assert not (marker_dir / "pip_check.marker").exists()
        assert not (marker_dir / "demo.marker").exists()
        assert not (marker_dir / "demo_research.marker").exists()

    def test_quick_fails_when_dev_check_fails(self, tmp_path: Path) -> None:
        marker_dir = self._setup_fake_repo(tmp_path)
        env = os.environ.copy()
        env["PATH"] = f"{tmp_path / 'bin'}:{env.get('PATH', '')}"
        env["DEV_CHECK_EXIT"] = "1"

        result = _run_shell(
            tmp_path / "scripts" / "release_check.sh",
            cwd=tmp_path,
            env=env,
            args=["--quick"],
        )

        assert result.returncode != 0
        assert (marker_dir / "dev_check.marker").exists()

    def test_research_runs_research_check(self, tmp_path: Path) -> None:
        marker_dir = self._setup_fake_repo(tmp_path)
        env = os.environ.copy()
        env["PATH"] = f"{tmp_path / 'bin'}:{env.get('PATH', '')}"
        env["RESEARCH_CHECK_EXIT"] = "0"

        result = _run_shell(
            tmp_path / "scripts" / "release_check.sh",
            cwd=tmp_path,
            env=env,
            args=["--research"],
        )

        assert result.returncode == 0
        assert (marker_dir / "research_check.marker").exists()
        assert not (marker_dir / "pytest.marker").exists()
        assert not (marker_dir / "pip_check.marker").exists()
        assert not (marker_dir / "demo.marker").exists()

    def test_research_fails_when_research_check_fails(self, tmp_path: Path) -> None:
        marker_dir = self._setup_fake_repo(tmp_path)
        env = os.environ.copy()
        env["PATH"] = f"{tmp_path / 'bin'}:{env.get('PATH', '')}"
        env["RESEARCH_CHECK_EXIT"] = "1"

        result = _run_shell(
            tmp_path / "scripts" / "release_check.sh",
            cwd=tmp_path,
            env=env,
            args=["--research"],
        )

        assert result.returncode != 0
        assert (marker_dir / "research_check.marker").exists()

    def test_full_explicit_runs_full_gate(self, tmp_path: Path) -> None:
        marker_dir = self._setup_fake_repo(tmp_path)
        env = os.environ.copy()
        env["PATH"] = f"{tmp_path / 'bin'}:{env.get('PATH', '')}"
        env["PYTEST_EXIT"] = "0"
        env["PIP_CHECK_EXIT"] = "0"
        env["DEMO_EXIT"] = "0"
        env["GIT_DIFF_EXIT"] = "0"
        env["VERSION_EXIT"] = "0"
        env["CLAIMS_EXIT"] = "0"

        result = _run_shell(
            tmp_path / "scripts" / "release_check.sh",
            cwd=tmp_path,
            env=env,
            args=["--full"],
        )

        assert result.returncode == 0
        assert (marker_dir / "pytest.marker").exists()
        assert (marker_dir / "pip_check.marker").exists()
        assert (marker_dir / "demo.marker").exists()
        assert (marker_dir / "git_diff.marker").exists()
        assert (marker_dir / "version.marker").exists()
        assert (marker_dir / "claims.marker").exists()

    def test_unknown_flag_fails(self, tmp_path: Path) -> None:
        self._setup_fake_repo(tmp_path)
        env = os.environ.copy()
        env["PATH"] = f"{tmp_path / 'bin'}:{env.get('PATH', '')}"

        result = _run_shell(
            tmp_path / "scripts" / "release_check.sh",
            cwd=tmp_path,
            env=env,
            args=["--unknown-flag"],
        )

        assert result.returncode != 0
        assert "Unknown option" in (result.stdout + result.stderr)

    def test_help_exits_zero(self, tmp_path: Path) -> None:
        self._setup_fake_repo(tmp_path)
        env = os.environ.copy()
        env["PATH"] = f"{tmp_path / 'bin'}:{env.get('PATH', '')}"

        result = _run_shell(
            tmp_path / "scripts" / "release_check.sh",
            cwd=tmp_path,
            env=env,
            args=["--help"],
        )

        assert result.returncode == 0
        assert "Usage:" in result.stdout


# ---------------------------------------------------------------------------
# dev_check.sh
# ---------------------------------------------------------------------------

class TestDevCheckSh:
    def test_exists_and_is_executable(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        script = repo_root / "scripts" / "dev_check.sh"
        assert script.exists()
        assert script.stat().st_mode & 0o111, "dev_check.sh should be executable"

    def test_contains_expected_checks(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        content = (repo_root / "scripts" / "dev_check.sh").read_text(encoding="utf-8")

        assert "check_release_metadata.py" in content
        assert "check_version_consistency.py" in content
        assert "check_forbidden_claims.py" in content
        assert "check_trust_center.py" in content
        assert "check_onboarding_docs.py" in content
        assert "check_generated_artifacts.py" in content
        assert "check_template_parity.py" in content
        assert "check_github_actions_versions.py" in content
        assert "tests/test_generated_artifacts.py" in content
        assert "tests/test_github_actions_versions.py" in content
        assert "tests/test_template_parity.py" in content
        assert "tests/research/test_research_sandbox_cli.py" in content
        assert "tests/test_release_check_scripts.py" in content
        assert "git diff --check" in content
        assert "git diff --cached --check" in content
        assert "check_no_protected_staged.py" in content

    def test_does_not_run_expensive_checks(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        content = (repo_root / "scripts" / "dev_check.sh").read_text(encoding="utf-8")

        assert "demo_paper_workflow" not in content
        assert "demo_research_workflow" not in content
        assert "pip check" not in content
        # Should not run full pytest without a test path
        assert "pytest -q\n" not in content
        assert "pytest -q \"" not in content

    def test_static_mutation_guard(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        content = (repo_root / "scripts" / "dev_check.sh").read_text(encoding="utf-8")

        forbidden = [
            "git add",
            "git commit",
            "git push",
            "git checkout",
            "git reset",
            "git clean",
            "git restore",
            "git switch",
            "gh release",
            "rm -rf .git",
            "sed -i",
            "perl -pi",
            "tee -a",
        ]
        for pattern in forbidden:
            assert pattern not in content, f"dev_check.sh contains forbidden pattern: {pattern}"


# ---------------------------------------------------------------------------
# research_check.sh
# ---------------------------------------------------------------------------

class TestResearchCheckSh:
    def test_exists_and_is_executable(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        script = repo_root / "scripts" / "research_check.sh"
        assert script.exists()
        assert script.stat().st_mode & 0o111, "research_check.sh should be executable"

    def test_contains_expected_checks(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        content = (repo_root / "scripts" / "research_check.sh").read_text(encoding="utf-8")


        assert "check_version_consistency.py" in content
        assert "check_forbidden_claims.py" in content
        assert "tests/research" in content
        assert "tests/test_demo_research_workflow_script.py" in content
        assert "demo_research_workflow.sh" in content
        assert "git diff --check" in content
        assert "git diff --cached --check" in content
        assert "check_no_protected_staged.py" in content

    def test_does_not_run_full_pytest_or_paper_demo(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        content = (repo_root / "scripts" / "research_check.sh").read_text(encoding="utf-8")

        assert "demo_paper_workflow" not in content
        assert "pip check" not in content
        # Should not run full pytest without a test path
        assert "pytest -q\n" not in content
        assert "pytest -q \"" not in content

    def test_static_mutation_guard(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        content = (repo_root / "scripts" / "research_check.sh").read_text(encoding="utf-8")

        forbidden = [
            "git add",
            "git commit",
            "git push",
            "git checkout",
            "git reset",
            "git clean",
            "git restore",
            "git switch",
            "gh release",
            "rm -rf .git",
            "sed -i",
            "perl -pi",
            "tee -a",
        ]
        for pattern in forbidden:
            assert pattern not in content, f"research_check.sh contains forbidden pattern: {pattern}"


# ---------------------------------------------------------------------------
# release_check.sh tiered mode guards
# ---------------------------------------------------------------------------

class TestReleaseCheckTieredModes:
    def test_contains_mode_flags(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        content = (repo_root / "scripts" / "release_check.sh").read_text(encoding="utf-8")

        assert "--quick)" in content
        assert "--research)" in content
        assert "--full)" in content

    def test_quick_delegates_to_dev_check(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        content = (repo_root / "scripts" / "release_check.sh").read_text(encoding="utf-8")

        assert "dev_check.sh" in content

    def test_research_delegates_to_research_check(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        content = (repo_root / "scripts" / "release_check.sh").read_text(encoding="utf-8")

        assert "research_check.sh" in content

    def test_full_contains_all_checks(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        content = (repo_root / "scripts" / "release_check.sh").read_text(encoding="utf-8")

        assert "pytest -q" in content
        assert "pip check" in content
        assert "demo_paper_workflow.sh" in content
        assert "demo_research_workflow.sh" in content
        assert "git diff --check" in content
        assert "git diff --cached --check" in content

        assert "check_version_consistency.py" in content
        assert "check_forbidden_claims.py" in content
        assert "check_no_protected_staged.py" in content

    def test_no_git_add_dot(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        content = (repo_root / "scripts" / "release_check.sh").read_text(encoding="utf-8")

        assert "git add ." not in content
        assert "git add" not in content

    def test_includes_per_step_timing(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        content = (repo_root / "scripts" / "release_check.sh").read_text(encoding="utf-8")

        assert "SECONDS=0" in content
        assert "elapsed: ${SECONDS}s" in content

    def test_includes_total_elapsed(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        content = (repo_root / "scripts" / "release_check.sh").read_text(encoding="utf-8")

        assert "Total elapsed: ${TOTAL_ELAPSED}s" in content

    def test_no_broad_or_true(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        content = (repo_root / "scripts" / "release_check.sh").read_text(encoding="utf-8")

        assert "|| true" not in content


# ---------------------------------------------------------------------------
# Timing coverage across gate scripts
# ---------------------------------------------------------------------------

class TestGateScriptTiming:
    def test_research_check_includes_timing(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        content = (repo_root / "scripts" / "research_check.sh").read_text(encoding="utf-8")

        assert "SECONDS=0" in content
        assert "elapsed: ${SECONDS}s" in content
        assert "Total elapsed: ${TOTAL_ELAPSED}s" in content

    def test_research_check_no_broad_or_true(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        content = (repo_root / "scripts" / "research_check.sh").read_text(encoding="utf-8")

        assert "|| true" not in content

    def test_dev_check_includes_timing(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        content = (repo_root / "scripts" / "dev_check.sh").read_text(encoding="utf-8")

        assert "SECONDS=0" in content
        assert "elapsed: ${SECONDS}s" in content
        assert "Total elapsed: ${TOTAL_ELAPSED}s" in content

    def test_ci_check_includes_timing(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        content = (repo_root / "scripts" / "ci_check.sh").read_text(encoding="utf-8")

        assert "SECONDS=0" in content
        assert "elapsed: ${SECONDS}s" in content
        assert "Total elapsed: ${TOTAL_ELAPSED}s" in content
