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


def _run_shell(script_path: Path, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["/bin/bash", str(script_path)],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )
    return result


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

        result = _run_script("check_version_consistency.py", str(tmp_path))
        assert result.returncode == 2
        assert "mismatch" in result.stdout.lower() or "failed" in result.stdout.lower()

    def test_missing_pyproject(self, tmp_path: Path) -> None:
        init_dir = tmp_path / "src" / "atlas_agent"
        init_dir.mkdir(parents=True)
        init_file = init_dir / "__init__.py"
        init_file.write_text('__version__ = "1.0.0"\n', encoding="utf-8")

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

        # Fake git
        fake_git = bin_dir / "git"
        fake_git.write_text(
            '#!/usr/bin/env bash\n'
            'set -euo pipefail\n'
            'MARKER_DIR="' + str(marker_dir) + '"\n'
            'if [[ "$1" == "diff" && "$2" == "--check" ]]; then\n'
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

        # Stub pyproject.toml and __init__.py so version check passes when called
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nversion = "0.0.0"\n', encoding="utf-8")
        init_dir = tmp_path / "src" / "atlas_agent"
        init_dir.mkdir(parents=True)
        init_file = init_dir / "__init__.py"
        init_file.write_text('__version__ = "0.0.0"\n', encoding="utf-8")

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
