"""Tests for contributor onboarding documentation consistency.

Docs/checker only. No network, credentials, provider calls, broker calls, tag
creation, release creation, package publishing, or runtime execution changes.
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
SCRIPT = REPO_ROOT / "scripts" / "check_onboarding_docs.py"


def _load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_onboarding_docs_for_tests", SCRIPT)
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
    return subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _valid_fixture(tmp_path: Path) -> Path:
    for rel_path in CHECKER.REQUIRED_DOCS:
        _write(
            tmp_path / rel_path,
            (REPO_ROOT / rel_path).read_text(encoding="utf-8"),
        )
    return tmp_path


def _rewrite_docs(repo_root: Path, transform: Callable[[str], str]) -> None:
    for rel_path in CHECKER.REQUIRED_DOCS:
        path = repo_root / rel_path
        path.write_text(transform(path.read_text(encoding="utf-8")), encoding="utf-8")


class TestOnboardingDocsChecker:
    def test_onboarding_docs_checker_passes_on_current_docs(self) -> None:
        result = _run_checker(REPO_ROOT)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Onboarding docs check PASSED" in result.stdout

    def test_fails_if_python_311_mention_missing(self, tmp_path: Path) -> None:
        repo = _valid_fixture(tmp_path)
        _rewrite_docs(
            repo,
            lambda text: text.replace("Python 3.11", "Python 3.10").replace(
                "python3.11",
                "python3.10",
            ),
        )

        result = _run_checker(repo)
        assert result.returncode == 1
        assert "Python 3.11" in result.stdout

    def test_fails_if_dev_extras_install_missing(self, tmp_path: Path) -> None:
        repo = _valid_fixture(tmp_path)
        _rewrite_docs(
            repo,
            lambda text: text.replace('python -m pip install -e ".[dev]"', "").replace(
                "dev extras",
                "development dependencies",
            ),
        )

        result = _run_checker(repo)
        assert result.returncode == 1
        assert "dev extras install" in result.stdout

    def test_fails_if_no_real_credentials_note_missing(self, tmp_path: Path) -> None:
        repo = _valid_fixture(tmp_path)
        _rewrite_docs(repo, lambda text: re.sub(r"^.*real credentials.*\n", "", text, flags=re.I | re.M))

        result = _run_checker(repo)
        assert result.returncode == 1
        assert "no real credentials required" in result.stdout

    def test_fails_if_live_trading_disabled_note_missing(self, tmp_path: Path) -> None:
        repo = _valid_fixture(tmp_path)
        _rewrite_docs(
            repo,
            lambda text: text.replace("Live trading is disabled by default.", "").replace(
                "live trading is disabled by default",
                "",
            ),
        )

        result = _run_checker(repo)
        assert result.returncode == 1
        assert "live trading disabled by default" in result.stdout

    def test_fails_if_provider_execution_disabled_note_missing(self, tmp_path: Path) -> None:
        repo = _valid_fixture(tmp_path)
        _rewrite_docs(
            repo,
            lambda text: text.replace("Provider execution is disabled by default.", "").replace(
                "provider execution is disabled by default",
                "",
            ),
        )

        result = _run_checker(repo)
        assert result.returncode == 1
        assert "provider execution disabled by default" in result.stdout

    def test_fails_if_release_assurance_command_missing(self, tmp_path: Path) -> None:
        repo = _valid_fixture(tmp_path)
        _rewrite_docs(repo, lambda text: text.replace("release_assurance.py", "release_assurance_removed"))

        result = _run_checker(repo)
        assert result.returncode == 1
        assert "release_assurance.py" in result.stdout

    def test_fails_if_provider_audit_pack_command_missing(self, tmp_path: Path) -> None:
        repo = _valid_fixture(tmp_path)
        _rewrite_docs(
            repo,
            lambda text: text.replace("providers audit-pack", "providers audit_removed").replace(
                "provider audit-pack",
                "provider audit removed",
            ),
        )

        result = _run_checker(repo)
        assert result.returncode == 1
        assert "provider audit-pack" in result.stdout

    def test_fails_if_dangerous_pattern_scan_missing(self, tmp_path: Path) -> None:
        repo = _valid_fixture(tmp_path)
        _rewrite_docs(repo, lambda text: re.sub(r"^git diff \| grep -n -E .*\n", "", text, flags=re.M))

        result = _run_checker(repo)
        assert result.returncode == 1
        assert "dangerous-pattern scan" in result.stdout

    def test_fails_if_destructive_git_command_is_normal_workflow(self, tmp_path: Path) -> None:
        repo = _valid_fixture(tmp_path)
        doc = repo / CHECKER.ONBOARDING_DOC
        doc.write_text(
            doc.read_text(encoding="utf-8")
            + "\n## Normal Workflow\n\n```bash\ngit reset --hard\n```\n",
            encoding="utf-8",
        )

        result = _run_checker(repo)
        assert result.returncode == 1
        assert "outside warning/approval context" in result.stdout

    def test_fails_on_secret_like_values(self, tmp_path: Path) -> None:
        repo = _valid_fixture(tmp_path)
        fake_value = "sk-" + ("x" * 24)
        doc = repo / CHECKER.ONBOARDING_DOC
        doc.write_text(
            doc.read_text(encoding="utf-8") + f"\n\n{fake_value}\n",
            encoding="utf-8",
        )

        result = _run_checker(repo)
        assert result.returncode == 1
        assert "secret-like value" in result.stdout

    def test_json_mode_works(self) -> None:
        result = _run_checker(REPO_ROOT, json_mode=True)
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["artifact_type"] == "atlas_onboarding_docs_check"
        assert payload["status"] == "passed"
        assert payload["exit_code"] == 0
        assert payload["findings"] == []
