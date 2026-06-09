#!/usr/bin/env python3
"""Local contributor environment diagnostics for Atlas Agent.

The doctor is read-only. It does not install dependencies, edit files, create
branches, stage changes, commit, push, tag, release, publish packages, call
providers, call brokers, read credential files, or print secret values.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


CURRENT_RELEASE_TAG = "v0.6.6"
REQUIRED_DEV_SCRIPTS = [
    "scripts/check_version_consistency.py",
    "scripts/check_forbidden_claims.py",
    "scripts/check_trust_center.py",
    "scripts/check_onboarding_docs.py",
    "scripts/dev_check.sh",
    "scripts/ci_check.sh",
    "scripts/release_check.sh",
]
REQUIRED_TRUST_DOCS = [
    "docs/trust/README.md",
    "docs/trust/v0.6.6-status.md",
]
TRACKED_SECRET_FILENAMES = {
    ".env",
    ".env.atlas",
    ".env.local",
    ".pypirc",
    "credentials.json",
    "credentials.yml",
    "credentials.yaml",
    "secrets.json",
    "secrets.yml",
    "secrets.yaml",
    "api_keys.json",
    "tokens.json",
    "passwords.txt",
    "id_rsa",
    "id_ed25519",
}


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class DoctorCheck:
    id: str
    status: str
    detail: str


@dataclass(frozen=True)
class DoctorReport:
    repo_root: str
    checks: list[DoctorCheck]
    warnings: list[str]
    findings: list[str]
    errors: list[str]
    branch: str | None
    dirty_worktree: bool | None

    @property
    def valid(self) -> bool:
        return not self.errors and not self.findings and not self.warnings

    @property
    def exit_code(self) -> int:
        if self.errors:
            return 2
        if self.findings or self.warnings:
            return 1
        return 0

    @property
    def status(self) -> str:
        if self.errors:
            return "error"
        if self.findings or self.warnings:
            return "warning"
        return "passed"

    def to_jsonable(self) -> dict[str, object]:
        return {
            "artifact_type": "atlas_doctor_report",
            "schema_version": 1,
            "valid": self.valid,
            "status": self.status,
            "exit_code": self.exit_code,
            "repo_root": self.repo_root,
            "branch": self.branch,
            "dirty_worktree": self.dirty_worktree,
            "checks": {check.id: check.status == "pass" for check in self.checks},
            "check_results": [check.__dict__ for check in self.checks],
            "warnings": self.warnings,
            "findings": self.findings,
            "errors": self.errors,
        }


def run_cmd(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> CommandResult:
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return CommandResult(127, "", str(exc))
    return CommandResult(result.returncode, result.stdout, result.stderr)


def _add_check(
    checks: list[DoctorCheck],
    sink: list[str],
    check_id: str,
    ok: bool,
    pass_detail: str,
    fail_detail: str,
    *,
    status_on_fail: str = "fail",
) -> None:
    if ok:
        checks.append(DoctorCheck(check_id, "pass", pass_detail))
        return
    checks.append(DoctorCheck(check_id, status_on_fail, fail_detail))
    sink.append(fail_detail)


def _tracked_secret_files(paths: list[str]) -> list[str]:
    matches: list[str] = []
    for raw in paths:
        path = raw.strip()
        if not path:
            continue
        name = Path(path).name.lower()
        if name in TRACKED_SECRET_FILENAMES:
            matches.append(path)
    return sorted(set(matches))


def run_doctor(
    repo_root: Path,
    *,
    cwd: Path | None = None,
    command_runner=run_cmd,
    which=shutil.which,
) -> DoctorReport:
    repo_root = repo_root.resolve()
    cwd = (cwd or Path.cwd()).resolve()
    checks: list[DoctorCheck] = []
    warnings: list[str] = []
    findings: list[str] = []
    errors: list[str] = []
    branch: str | None = None
    dirty_worktree: bool | None = None

    _add_check(
        checks,
        findings,
        "python_version",
        sys.version_info >= (3, 11),
        f"Python version is {sys.version_info.major}.{sys.version_info.minor}",
        f"Python >= 3.11 required, got {sys.version_info.major}.{sys.version_info.minor}",
    )
    _add_check(
        checks,
        findings,
        "repo_root",
        cwd == repo_root,
        f"running from repo root: {repo_root}",
        f"run doctor from repo root: cwd={cwd} repo_root={repo_root}",
    )
    _add_check(
        checks,
        findings,
        "pyproject_present",
        (repo_root / "pyproject.toml").is_file(),
        "pyproject.toml exists",
        "pyproject.toml is missing",
    )
    _add_check(
        checks,
        findings,
        "init_present",
        (repo_root / "src" / "atlas_agent" / "__init__.py").is_file(),
        "src/atlas_agent/__init__.py exists",
        "src/atlas_agent/__init__.py is missing",
    )
    missing_dev_scripts = [path for path in REQUIRED_DEV_SCRIPTS if not (repo_root / path).exists()]
    _add_check(
        checks,
        findings,
        "dev_scripts_present",
        not missing_dev_scripts,
        "required dev scripts exist",
        f"missing dev scripts: {', '.join(missing_dev_scripts)}",
    )
    missing_trust_docs = [path for path in REQUIRED_TRUST_DOCS if not (repo_root / path).exists()]
    _add_check(
        checks,
        findings,
        "trust_center_present",
        not missing_trust_docs,
        "trust center docs exist",
        f"missing trust center docs: {', '.join(missing_trust_docs)}",
    )
    _add_check(
        checks,
        findings,
        "release_assurance_present",
        (repo_root / "scripts" / "release_assurance.py").is_file(),
        "release assurance script exists",
        "scripts/release_assurance.py is missing",
    )

    env = os.environ.copy()
    src_path = str(repo_root / "src")
    env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    help_result = command_runner(
        [sys.executable, "-m", "atlas_agent.cli", "providers", "audit-pack", "--help"],
        cwd=repo_root,
        env=env,
    )
    _add_check(
        checks,
        warnings,
        "provider_audit_pack_help",
        help_result.returncode == 0,
        "provider audit-pack CLI help works",
        "provider audit-pack CLI help did not run; install dev extras and retry",
        status_on_fail="warn",
    )

    git_path = which("git")
    _add_check(
        checks,
        warnings,
        "git_available",
        bool(git_path),
        "git is available",
        "git is not available on PATH",
        status_on_fail="warn",
    )

    tracked_files: list[str] = []
    if git_path:
        branch_result = command_runner(["git", "branch", "--show-current"], cwd=repo_root)
        if branch_result.returncode == 0:
            branch = branch_result.stdout.strip() or None
            checks.append(
                DoctorCheck(
                    "current_branch",
                    "pass" if branch else "warn",
                    f"current branch: {branch or 'detached HEAD'}",
                )
            )
            if not branch:
                warnings.append("current git state appears to be detached HEAD")
        else:
            checks.append(DoctorCheck("current_branch", "warn", "could not determine current branch"))
            warnings.append("could not determine current branch")

        status_result = command_runner(["git", "status", "--porcelain"], cwd=repo_root)
        if status_result.returncode == 0:
            dirty_worktree = bool(status_result.stdout.strip())
            _add_check(
                checks,
                warnings,
                "dirty_worktree_status",
                not dirty_worktree,
                "worktree is clean",
                "worktree has local modifications or untracked files",
                status_on_fail="warn",
            )
        else:
            checks.append(DoctorCheck("dirty_worktree_status", "warn", "could not determine worktree status"))
            warnings.append("could not determine worktree status")

        tag_result = command_runner(["git", "tag", "-l", CURRENT_RELEASE_TAG], cwd=repo_root)
        _add_check(
            checks,
            warnings,
            "release_tag_present",
            tag_result.returncode == 0 and tag_result.stdout.strip() == CURRENT_RELEASE_TAG,
            f"{CURRENT_RELEASE_TAG} tag exists locally",
            f"{CURRENT_RELEASE_TAG} tag is not present locally; fetch tags if release checks need it",
            status_on_fail="warn",
        )

        files_result = command_runner(["git", "ls-files", "-z"], cwd=repo_root)
        if files_result.returncode == 0:
            tracked_files = [part for part in files_result.stdout.split("\0") if part]
        else:
            warnings.append("could not inspect tracked files for secret-like filenames")
            checks.append(
                DoctorCheck(
                    "tracked_files_available",
                    "warn",
                    "could not inspect tracked files for secret-like filenames",
                )
            )

    gh_path = which("gh")
    checks.append(
        DoctorCheck(
            "github_cli_available",
            "pass" if gh_path else "skip",
            "GitHub CLI is available" if gh_path else "GitHub CLI is not installed; optional for local checks",
        )
    )

    env_atlas_tracked = ".env.atlas" in tracked_files
    _add_check(
        checks,
        findings,
        "no_env_atlas_tracked",
        not env_atlas_tracked,
        ".env.atlas is not tracked",
        ".env.atlas is tracked and must be removed from version control",
    )
    secret_files = _tracked_secret_files(tracked_files)
    _add_check(
        checks,
        findings,
        "no_tracked_secret_files",
        not secret_files,
        "no obvious secret files are tracked",
        f"tracked secret-like filenames: {', '.join(secret_files)}",
    )

    return DoctorReport(
        repo_root=str(repo_root),
        checks=checks,
        warnings=warnings,
        findings=findings,
        errors=errors,
        branch=branch,
        dirty_worktree=dirty_worktree,
    )


def _print_text_report(report: DoctorReport) -> None:
    if report.status == "passed":
        print("Atlas doctor PASSED")
    elif report.status == "warning":
        print("Atlas doctor WARNINGS")
    else:
        print("Atlas doctor ERROR")

    print(f"  Repo root: {report.repo_root}")
    print(f"  Checks: {len(report.checks)}")
    if report.branch:
        print(f"  Branch: {report.branch}")
    if report.dirty_worktree is not None:
        print(f"  Dirty worktree: {'yes' if report.dirty_worktree else 'no'}")

    if report.errors:
        print("  Operational errors:")
        for error in report.errors:
            print(f"  - {error}")
    if report.findings:
        print("  Findings:")
        for finding in report.findings:
            print(f"  - {finding}")
    if report.warnings:
        print("  Warnings:")
        for warning in report.warnings:
            print(f"  - {warning}")
    if not report.errors and not report.findings and not report.warnings:
        print("  Findings: 0")
        print("  Warnings: 0")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run read-only Atlas Agent local diagnostics.")
    parser.add_argument(
        "repo_root",
        nargs="?",
        default=Path(__file__).resolve().parent.parent,
        type=Path,
        help="Repository root to inspect. Defaults to this script's repository.",
    )
    parser.add_argument("--json", action="store_true", help="Emit deterministic JSON output.")
    args = parser.parse_args(argv)

    try:
        report = run_doctor(args.repo_root)
    except OSError as exc:
        report = DoctorReport(
            repo_root=str(args.repo_root.resolve()),
            checks=[],
            warnings=[],
            findings=[],
            errors=[str(exc)],
            branch=None,
            dirty_worktree=None,
        )

    if args.json:
        print(json.dumps(report.to_jsonable(), indent=2, sort_keys=True))
    else:
        _print_text_report(report)
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
