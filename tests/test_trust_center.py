"""Tests for the public trust center consistency checker.

Docs/test/checker only. No network, credentials, provider calls, broker calls,
tag creation, release creation, package publishing, or runtime execution changes.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_trust_center.py"
TRUST_README = REPO_ROOT / "docs" / "trust" / "README.md"
TRUST_STATUS = REPO_ROOT / "docs" / "trust" / "v0.6.4-status.md"


def _load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_trust_center_for_tests", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CHECKER = _load_checker()


def _run_checker(repo_root: Path, *, json_mode: bool = False) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SCRIPT)]
    if json_mode:
        cmd.append("--json")
    cmd.append(str(repo_root))
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _valid_fixture(tmp_path: Path) -> Path:
    _write(tmp_path / "pyproject.toml", '[project]\nversion = "0.6.5"\n')
    _write(tmp_path / "src" / "atlas_agent" / "__init__.py", '__version__ = "0.6.5"\n')

    for rel_path in CHECKER.REQUIRED_LINKS:
        _write(tmp_path / rel_path, "# Fixture\n\nNot financial advice.\n")

    _write(tmp_path / "docs" / "trust" / "README.md", TRUST_README.read_text(encoding="utf-8"))
    _write(
        tmp_path / "docs" / "trust" / "v0.6.5-status.md",
        TRUST_STATUS.read_text(encoding="utf-8"),
    )
    return tmp_path


def _rewrite_trust_docs(repo_root: Path, transform: Callable[[str], str]) -> None:
    for rel_path in (CHECKER.TRUST_README, CHECKER.TRUST_STATUS):
        path = repo_root / rel_path
        path.write_text(transform(path.read_text(encoding="utf-8")), encoding="utf-8")


class TestTrustCenterFiles:
    def test_trust_center_files_exist(self) -> None:
        assert TRUST_README.is_file()
        assert TRUST_STATUS.is_file()


class TestTrustCenterChecker:
    def test_check_trust_center_passes_on_current_docs(self) -> None:
        result = _run_checker(REPO_ROOT)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Trust center check PASSED" in result.stdout

    def test_check_trust_center_json_mode_works(self) -> None:
        result = _run_checker(REPO_ROOT, json_mode=True)
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "passed"
        assert payload["exit_code"] == 0
        assert payload["findings"] == []

    def test_fails_on_stale_current_status_versions(self, tmp_path: Path) -> None:
        repo = _valid_fixture(tmp_path)
        readme = repo / CHECKER.TRUST_README
        readme.write_text(
            readme.read_text(encoding="utf-8")
            + "\n\nCurrent public release: v0.5.9.dev0\n",
            encoding="utf-8",
        )

        result = _run_checker(repo)
        assert result.returncode == 1
        assert "stale" in result.stdout.lower()
        assert "0.5.9.dev0" in result.stdout

    def test_fails_if_pypi_not_published_note_is_missing(self, tmp_path: Path) -> None:
        repo = _valid_fixture(tmp_path)
        _rewrite_trust_docs(repo, lambda text: re.sub(r"^.*PyPI.*\n", "", text, flags=re.M))

        result = _run_checker(repo)
        assert result.returncode == 1
        assert "PyPI not published" in result.stdout

    def test_fails_if_live_trading_default_note_is_missing(self, tmp_path: Path) -> None:
        repo = _valid_fixture(tmp_path)
        _rewrite_trust_docs(
            repo,
            lambda text: text.replace("- Live trading is disabled by default.\n", ""),
        )

        result = _run_checker(repo)
        assert result.returncode == 1
        assert "live trading disabled by default" in result.stdout

    def test_fails_if_provider_execution_default_note_is_missing(self, tmp_path: Path) -> None:
        repo = _valid_fixture(tmp_path)
        _rewrite_trust_docs(
            repo,
            lambda text: text.replace("- Provider execution is disabled by default.\n", ""),
        )

        result = _run_checker(repo)
        assert result.returncode == 1
        assert "provider execution disabled by default" in result.stdout

    def test_fails_if_autonomous_trading_non_claim_is_missing(self, tmp_path: Path) -> None:
        repo = _valid_fixture(tmp_path)
        _rewrite_trust_docs(
            repo,
            lambda text: re.sub(r"^.*Autonomous trading.*\n", "", text, flags=re.M),
        )

        result = _run_checker(repo)
        assert result.returncode == 1
        assert "autonomous trading non-claim" in result.stdout

    def test_fails_if_financial_advice_non_claim_is_missing(self, tmp_path: Path) -> None:
        repo = _valid_fixture(tmp_path)
        _rewrite_trust_docs(
            repo,
            lambda text: re.sub(r"^.*financial advice.*\n", "", text, flags=re.I | re.M),
        )

        result = _run_checker(repo)
        assert result.returncode == 1
        assert "financial advice non-claim" in result.stdout

    def test_fails_if_release_notes_link_is_missing(self, tmp_path: Path) -> None:
        repo = _valid_fixture(tmp_path)
        readme = repo / CHECKER.TRUST_README
        readme.write_text(
            readme.read_text(encoding="utf-8").replace("../releases/v0.6.4.md", "missing.md"),
            encoding="utf-8",
        )

        result = _run_checker(repo)
        assert result.returncode == 1
        assert "docs/releases/v0.6.4.md" in result.stdout

    def test_fails_if_security_link_is_missing(self, tmp_path: Path) -> None:
        repo = _valid_fixture(tmp_path)
        readme = repo / CHECKER.TRUST_README
        readme.write_text(
            readme.read_text(encoding="utf-8").replace("../../SECURITY.md", "missing.md"),
            encoding="utf-8",
        )

        result = _run_checker(repo)
        assert result.returncode == 1
        assert "SECURITY.md" in result.stdout

    def test_fails_if_provider_audit_pack_link_is_missing(self, tmp_path: Path) -> None:
        repo = _valid_fixture(tmp_path)
        readme = repo / CHECKER.TRUST_README
        readme.write_text(
            readme.read_text(encoding="utf-8").replace(
                "../security/provider-audit-pack.md",
                "missing.md",
            ),
            encoding="utf-8",
        )

        result = _run_checker(repo)
        assert result.returncode == 1
        assert "docs/security/provider-audit-pack.md" in result.stdout

    def test_fails_on_secret_like_values(self, tmp_path: Path) -> None:
        repo = _valid_fixture(tmp_path)
        fake_value = "sk-" + ("x" * 24)
        readme = repo / CHECKER.TRUST_README
        readme.write_text(
            readme.read_text(encoding="utf-8") + f"\n\n{fake_value}\n",
            encoding="utf-8",
        )

        result = _run_checker(repo)
        assert result.returncode == 1
        assert "secret-like value" in result.stdout

    def test_no_protected_runtime_boundary_diff(self) -> None:
        protected_paths = [
            "src/atlas_agent/config",
            "src/atlas_agent/brokers",
            "src/atlas_agent/execution",
            "src/atlas_agent/safety",
            "src/atlas_agent/risk",
        ]
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "--", *protected_paths],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == ""


class TestPypiNonPublishConsistency:
    def test_trust_docs_use_consistent_pypi_not_published_phrasing(self) -> None:
        readme_text = TRUST_README.read_text(encoding="utf-8").lower()
        status_text = TRUST_STATUS.read_text(encoding="utf-8").lower()
        combined = readme_text + "\n" + status_text

        # Docs must state PyPI was not published
        assert "pypi was not published" in combined, (
            "Trust docs should use consistent 'PyPI was not published' phrasing"
        )

        # Docs must not claim PyPI publishing occurred
        assert "pypi publish has been performed" not in combined, (
            "Trust docs must not claim PyPI publish was performed"
        )
        assert "pypi published" not in combined.replace("pypi was not published", ""), (
            "Trust docs must not contain positive PyPI published claims"
        )

    def test_readme_uses_consistent_pypi_not_published_phrasing(self) -> None:
        readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8").lower()
        assert "pypi was not published" in readme_text, (
            "README should use consistent 'PyPI was not published' phrasing"
        )
        assert "pypi publish has been performed" not in readme_text, (
            "README must not claim PyPI publish was performed"
        )

    def test_release_notes_use_consistent_pypi_not_published_phrasing(self) -> None:
        for version in ("v0.6.5", "v0.6.4"):
            release_notes = (REPO_ROOT / "docs" / "releases" / f"{version}.md").read_text(encoding="utf-8").lower()
            assert "pypi was not published" in release_notes, (
                f"{version} release notes should use consistent 'PyPI was not published' phrasing"
            )
            assert "pypi publish has been performed" not in release_notes, (
                f"{version} release notes must not claim PyPI publish was performed"
            )

    def test_no_twine_upload_in_scripts(self) -> None:
        scripts_dir = REPO_ROOT / "scripts"
        for path in scripts_dir.glob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            assert "twine upload" not in text, (
                f"{path.name} must not contain twine upload command"
            )

    def test_no_twine_upload_in_workflows(self) -> None:
        workflows_dir = REPO_ROOT / ".github" / "workflows"
        for path in workflows_dir.glob("*.yml"):
            text = path.read_text(encoding="utf-8").lower()
            assert "twine upload" not in text, (
                f"{path.name} must not contain twine upload command"
            )
