"""Tests for the read-only contributor doctor script."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "doctor.py"


def _load_doctor() -> ModuleType:
    spec = importlib.util.spec_from_file_location("doctor_for_tests", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


DOCTOR = _load_doctor()


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _repo_fixture(tmp_path: Path) -> Path:
    _write(tmp_path / "pyproject.toml", '[project]\nversion = "0.5.9.3"\n')
    _write(tmp_path / "src" / "atlas_agent" / "__init__.py", '__version__ = "0.5.9.3"\n')
    for rel_path in DOCTOR.REQUIRED_DEV_SCRIPTS:
        _write(tmp_path / rel_path, "# fixture\n")
    for rel_path in DOCTOR.REQUIRED_TRUST_DOCS:
        _write(tmp_path / rel_path, "# fixture\n")
    _write(tmp_path / "scripts" / "release_assurance.py", "# fixture\n")
    _write(tmp_path / "README.md", "# fixture\n")
    return tmp_path


class FakeRunner:
    def __init__(self, *, tracked_files: list[str] | None = None, git_status: str = "") -> None:
        self.tracked_files = tracked_files or ["README.md"]
        self.git_status = git_status
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None):
        self.calls.append(cmd)
        if cmd[:5] == [sys.executable, "-m", "atlas_agent.cli", "providers", "audit-pack"]:
            return DOCTOR.CommandResult(0, "usage: audit-pack\n", "")
        if cmd == ["git", "branch", "--show-current"]:
            return DOCTOR.CommandResult(0, "main\n", "")
        if cmd == ["git", "status", "--porcelain"]:
            return DOCTOR.CommandResult(0, self.git_status, "")
        if cmd == ["git", "tag", "-l", DOCTOR.CURRENT_RELEASE_TAG]:
            return DOCTOR.CommandResult(0, f"{DOCTOR.CURRENT_RELEASE_TAG}\n", "")
        if cmd == ["git", "ls-files", "-z"]:
            return DOCTOR.CommandResult(0, "\0".join(self.tracked_files) + "\0", "")
        return DOCTOR.CommandResult(1, "", "unexpected command")


def _which(name: str) -> str | None:
    if name == "git":
        return "/usr/bin/git"
    return None


class TestDoctorScript:
    def test_doctor_text_mode_runs(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode in {0, 1}
        assert "Atlas doctor" in result.stdout

    def test_doctor_json_mode_returns_expected_artifact_type(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--json"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode in {0, 1}
        payload = json.loads(result.stdout)
        assert payload["artifact_type"] == "atlas_doctor_report"

    def test_doctor_reports_python_version_check(self, tmp_path: Path) -> None:
        repo = _repo_fixture(tmp_path)
        report = DOCTOR.run_doctor(repo, cwd=repo, command_runner=FakeRunner(), which=_which)
        payload = report.to_jsonable()
        assert "python_version" in payload["checks"]
        assert payload["checks"]["python_version"] is True

    def test_doctor_reports_repo_root_check(self, tmp_path: Path) -> None:
        repo = _repo_fixture(tmp_path)
        report = DOCTOR.run_doctor(repo, cwd=repo, command_runner=FakeRunner(), which=_which)
        assert report.to_jsonable()["checks"]["repo_root"] is True

    def test_doctor_reports_trust_center_present(self, tmp_path: Path) -> None:
        repo = _repo_fixture(tmp_path)
        report = DOCTOR.run_doctor(repo, cwd=repo, command_runner=FakeRunner(), which=_which)
        assert report.to_jsonable()["checks"]["trust_center_present"] is True

    def test_doctor_reports_release_assurance_present(self, tmp_path: Path) -> None:
        repo = _repo_fixture(tmp_path)
        report = DOCTOR.run_doctor(repo, cwd=repo, command_runner=FakeRunner(), which=_which)
        assert report.to_jsonable()["checks"]["release_assurance_present"] is True

    def test_doctor_does_not_print_fake_secret_env_values(self) -> None:
        fake_value = "sk-" + ("x" * 24)
        env = os.environ.copy()
        env["ATLAS_FAKE_SECRET_VALUE"] = fake_value
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env=env,
        )
        assert result.returncode in {0, 1}
        combined_output = result.stdout + result.stderr
        assert fake_value not in combined_output

    def test_doctor_does_not_modify_files(self, tmp_path: Path) -> None:
        repo = _repo_fixture(tmp_path)
        before = {
            path.relative_to(repo): path.read_bytes()
            for path in repo.rglob("*")
            if path.is_file()
        }

        report = DOCTOR.run_doctor(repo, cwd=repo, command_runner=FakeRunner(), which=_which)

        after = {
            path.relative_to(repo): path.read_bytes()
            for path in repo.rglob("*")
            if path.is_file()
        }
        assert report.exit_code == 0
        assert after == before

    def test_doctor_handles_missing_git_gracefully(self, tmp_path: Path) -> None:
        repo = _repo_fixture(tmp_path)

        def missing_git(name: str) -> str | None:
            return None

        report = DOCTOR.run_doctor(repo, cwd=repo, command_runner=FakeRunner(), which=missing_git)

        assert report.exit_code == 1
        assert report.errors == []
        assert report.to_jsonable()["checks"]["git_available"] is False
        assert "git is not available on PATH" in report.warnings

    def test_doctor_flags_tracked_secret_like_filenames(self, tmp_path: Path) -> None:
        repo = _repo_fixture(tmp_path)
        runner = FakeRunner(tracked_files=["README.md", ".env.atlas", "secrets.json"])

        report = DOCTOR.run_doctor(repo, cwd=repo, command_runner=runner, which=_which)

        assert report.exit_code == 1
        assert report.to_jsonable()["checks"]["no_env_atlas_tracked"] is False
        assert report.to_jsonable()["checks"]["no_tracked_secret_files"] is False
        assert any(".env.atlas" in finding for finding in report.findings)
        assert any("secrets.json" in finding for finding in report.findings)
