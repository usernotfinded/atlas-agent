#!/usr/bin/env python3
"""Report direct-main post-push health from local git metadata."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable, Iterable


@dataclass(frozen=True)
class ReleaseMetadata:
    """Central release metadata for main_health.py.

    Update these constants after each release cutover.
    The validate() method detects drift against the actual repo state.
    """

    expected_source_version: str
    public_release: str
    next_unrequested_release_tag: str

    def validate(
        self,
        source_version: str | None,
        git_runner: GitRunner,
        repo_root: Path,
    ) -> list[Finding]:
        """Return findings if release metadata appears stale."""
        findings: list[Finding] = []
        if source_version is not None and source_version != self.expected_source_version:
            findings.append(
                _finding(
                    "release_metadata_drift",
                    "EXPECTED_SOURCE_VERSION is "
                    f"{self.expected_source_version} but source version is {source_version}; "
                    "update ReleaseMetadata in main_health.py after release cutover",
                )
            )
        try:
            result = git_runner(repo_root, ["tag", "--list", self.public_release])
        except (FileNotFoundError, OSError):
            return findings
        if result.returncode == 0 and not result.stdout.strip():
            findings.append(
                _finding(
                    "public_release_tag_missing",
                    f"PUBLIC_RELEASE {self.public_release} has no matching local git tag; "
                    "update ReleaseMetadata in main_health.py after release cutover",
                )
            )
        try:
            result = git_runner(repo_root, ["tag", "--list", self.next_unrequested_release_tag])
        except (FileNotFoundError, OSError):
            return findings
        if result.returncode == 0 and result.stdout.strip():
            findings.append(
                _finding(
                    "next_release_tag_exists",
                    "NEXT_UNREQUESTED_RELEASE_TAG "
                    f"{self.next_unrequested_release_tag} already exists as a local tag; "
                    "update ReleaseMetadata in main_health.py after release cutover",
                )
            )
        return findings


RELEASE_METADATA = ReleaseMetadata(
    expected_source_version="0.6.5",
    public_release="v0.6.5",
    next_unrequested_release_tag="v0.6.6",
)

PROTECTED_BOUNDARIES = (
    "src/atlas_agent/config",
    "src/atlas_agent/brokers",
    "src/atlas_agent/execution",
    "src/atlas_agent/safety",
    "src/atlas_agent/risk",
)

LOCAL_ONLY_ARTIFACT_PREFIXES = (
    "artifacts/release_evidence/",
    "artifacts/release_assurance/",
    "artifacts/provider_audit_pack/",
    "artifacts/provider_preflight/",
    "artifacts/provider_preflight_bundles/",
    "artifacts/provider_preflight_smoke/",
)

RELEASE_PUBLISH_STAGED_PREFIXES = (
    "dist/",
    "build/",
    "artifacts/release_evidence/",
    f"artifacts/release_assurance/{RELEASE_METADATA.next_unrequested_release_tag}/",
)

RELEASE_PUBLISH_STAGED_EXACT = {
    f"docs/releases/{RELEASE_METADATA.next_unrequested_release_tag}.md",
}

RELEASE_PUBLISH_STAGED_SUFFIXES = (
    ".whl",
    ".tar.gz",
)

SECRET_VALUE_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9][A-Za-z0-9_-]{8,}"),
    re.compile(
        r"(?i)((?:api[._-]?key|token|password|secret)[^/]{0,12}[=:_-])"
        r"[A-Za-z0-9._~+=-]{8,}"
    ),
)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class Finding:
    code: str
    detail: str
    path: str = ""

    def to_jsonable(self) -> dict[str, str]:
        payload = {
            "code": self.code,
            "detail": self.detail,
        }
        if self.path:
            payload["path"] = self.path
        return payload


@dataclass(frozen=True)
class MainHealthReport:
    repo_root: str
    source_version: str | None
    public_release: str
    head_commit: str | None
    origin_main_commit: str | None
    checks: dict[str, bool]
    github: dict[str, object]
    warnings: list[Finding]
    findings: list[Finding]
    errors: list[str]

    @property
    def valid(self) -> bool:
        return not self.findings and not self.errors

    @property
    def exit_code(self) -> int:
        if self.errors:
            return 2
        if self.findings:
            return 1
        return 0

    def to_jsonable(self) -> dict[str, object]:
        return {
            "artifact_type": "atlas_main_health_report",
            "schema_version": 1,
            "valid": self.valid,
            "repo_root": self.repo_root,
            "source_version": self.source_version,
            "public_release": self.public_release,
            "head_commit": self.head_commit,
            "origin_main_commit": self.origin_main_commit,
            "checks": self.checks,
            "github": self.github,
            "warnings": [warning.to_jsonable() for warning in self.warnings],
            "findings": [finding.to_jsonable() for finding in self.findings],
            "errors": self.errors,
        }


GitRunner = Callable[[Path, list[str]], CommandResult]
GhRunner = Callable[[Path, list[str]], CommandResult]


def _run_git(repo_root: Path, args: list[str]) -> CommandResult:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return CommandResult(result.returncode, result.stdout, result.stderr)


def _run_gh(repo_root: Path, args: list[str]) -> CommandResult:
    result = subprocess.run(
        ["gh", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return CommandResult(result.returncode, result.stdout, result.stderr)


def _sanitize(text: str) -> str:
    sanitized = text
    for pattern in SECRET_VALUE_PATTERNS:
        sanitized = pattern.sub(
            lambda match: (
                match.group(1) + "[REDACTED]"
                if match.lastindex
                else "[REDACTED]"
            ),
            sanitized,
        )
    return sanitized


def _finding(code: str, detail: str, path: str = "") -> Finding:
    safe_path = _sanitize(path)
    safe_detail = _sanitize(detail.format(path=safe_path))
    return Finding(code=code, detail=safe_detail, path=safe_path)


def _split_paths(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip()]


def _parse_status(output: str) -> list[tuple[str, str]]:
    paths: list[tuple[str, str]] = []
    for line in output.splitlines():
        if not line.strip() or len(line) < 4:
            continue
        status = line[:2]
        path = line[3:].strip()
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[-1].strip()
        if path:
            paths.append((status, path))
    return paths


def _is_under(path: str, prefixes: Iterable[str]) -> bool:
    return any(path.startswith(prefix) for prefix in prefixes)


def _is_local_only_artifact(path: str) -> bool:
    return _is_under(path, LOCAL_ONLY_ARTIFACT_PREFIXES)


def _is_release_publish_staged_artifact(path: str) -> bool:
    if path in RELEASE_PUBLISH_STAGED_EXACT:
        return True
    if _is_under(path, RELEASE_PUBLISH_STAGED_PREFIXES):
        return True
    return path.endswith(RELEASE_PUBLISH_STAGED_SUFFIXES)


def _read_pyproject_version(path: Path) -> str | None:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    version = data.get("project", {}).get("version")
    return version if isinstance(version, str) else None


def _read_init_version(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    match = re.search(
        r'^__version__\s*=\s*["\']([^"\']+)["\']',
        text,
        re.MULTILINE,
    )
    return match.group(1) if match else None


def _load_generated_artifact_checker(repo_root: Path) -> ModuleType | None:
    checker_path = repo_root / "scripts" / "check_generated_artifacts.py"
    if not checker_path.exists():
        return None
    spec = importlib.util.spec_from_file_location(
        "atlas_main_health_generated_artifacts",
        checker_path,
    )
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _collect_generated_artifact_hygiene(
    repo_root: Path,
    git_runner: GitRunner,
    checks: dict[str, bool],
    warnings: list[Finding],
    findings: list[Finding],
    errors: list[str],
) -> None:
    module = _load_generated_artifact_checker(repo_root)
    checks["generated_artifact_checker_present"] = module is not None
    checks["generated_artifact_hygiene"] = False
    if module is None:
        warnings.append(
            _finding(
                "generated_artifact_checker_missing",
                "generated artifact checker is not available",
            )
        )
        return

    def adapter(path: Path, args: list[str]):
        return git_runner(path, args)

    try:
        report = module.collect_report(repo_root, git_runner=adapter)
    except FileNotFoundError:
        errors.append("generated artifact checker could not run: git unavailable")
        return
    except OSError as exc:
        errors.append(f"generated artifact checker could not run: {_sanitize(str(exc))}")
        return

    checks["generated_artifact_hygiene"] = report.exit_code == 0
    for warning in report.warnings:
        warnings.append(
            _finding(
                warning.code,
                warning.detail,
                getattr(warning, "path", ""),
            )
        )
    for finding in report.findings:
        findings.append(
            _finding(
                finding.code,
                finding.detail,
                getattr(finding, "path", ""),
            )
        )
    errors.extend(_sanitize(error) for error in report.errors)


def _collect_github_visibility(
    repo_root: Path,
    include_github: bool,
    gh_runner: GhRunner,
    warnings: list[Finding],
) -> dict[str, object]:
    github: dict[str, object] = {
        "requested": include_github,
        "gh_available": None,
        "runs": [],
    }
    if not include_github:
        return github

    if shutil.which("gh") is None:
        github["gh_available"] = False
        warnings.append(
            _finding(
                "github_cli_missing",
                "GitHub CLI is not available; CI visibility was not checked",
            )
        )
        return github

    github["gh_available"] = True
    try:
        result = gh_runner(repo_root, ["run", "list", "--branch", "main", "--limit", "5"])
    except FileNotFoundError:
        github["gh_available"] = False
        warnings.append(
            _finding(
                "github_cli_missing",
                "GitHub CLI is not available; CI visibility was not checked",
            )
        )
        return github
    except OSError as exc:
        warnings.append(
            _finding(
                "github_cli_error",
                f"GitHub CLI visibility failed: {_sanitize(str(exc))}",
            )
        )
        return github

    if result.returncode != 0:
        warnings.append(
            _finding(
                "github_cli_unavailable",
                "GitHub CLI run listing failed: "
                + _sanitize(result.stderr.strip() or result.stdout.strip() or "no output"),
            )
        )
        return github

    runs = [_sanitize(line) for line in result.stdout.splitlines() if line.strip()]
    github["runs"] = runs
    if not runs:
        warnings.append(
            _finding(
                "github_runs_missing",
                "GitHub CLI returned no workflow runs for branch main",
            )
        )
    return github


def _new_checks() -> dict[str, bool]:
    return {
        "repo_root": False,
        "pyproject_present": False,
        "init_present": False,
        "version_consistent": False,
        "expected_source_version": False,
        "public_release_expected": True,
        "git_available": False,
        "on_main": False,
        "origin_main_resolved": False,
        "head_matches_origin_main": False,
        "working_tree_clean": False,
        "no_staged_changes": False,
        "generated_artifact_checker_present": False,
        "generated_artifact_hygiene": False,
        "trust_center_checker_present": False,
        "onboarding_checker_present": False,
        "no_unrequested_maintenance_tag": False,
        "no_known_release_publish_artifacts_staged": False,
        "protected_boundary_clean": False,
    }


def collect_report(
    repo_root: Path,
    *,
    include_github: bool = False,
    git_runner: GitRunner = _run_git,
    gh_runner: GhRunner = _run_gh,
) -> MainHealthReport:
    repo_root = repo_root.resolve()
    checks = _new_checks()
    warnings: list[Finding] = []
    findings: list[Finding] = []
    errors: list[str] = []
    source_version: str | None = None
    head_commit: str | None = None
    origin_main_commit: str | None = None

    pyproject_path = repo_root / "pyproject.toml"
    init_path = repo_root / "src" / "atlas_agent" / "__init__.py"
    checks["pyproject_present"] = pyproject_path.exists()
    checks["init_present"] = init_path.exists()

    pyproject_version: str | None = None
    init_version: str | None = None
    if not checks["pyproject_present"]:
        findings.append(_finding("pyproject_missing", "pyproject.toml is missing"))
    else:
        try:
            pyproject_version = _read_pyproject_version(pyproject_path)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            errors.append(f"could not read pyproject.toml: {_sanitize(str(exc))}")

    if not checks["init_present"]:
        findings.append(
            _finding("init_missing", "src/atlas_agent/__init__.py is missing")
        )
    else:
        try:
            init_version = _read_init_version(init_path)
        except OSError as exc:
            errors.append(f"could not read __init__.py: {_sanitize(str(exc))}")

    if pyproject_version is not None and init_version is not None:
        checks["version_consistent"] = pyproject_version == init_version
        source_version = pyproject_version if pyproject_version == init_version else None
        if not checks["version_consistent"]:
            findings.append(
                _finding(
                    "version_mismatch",
                    "pyproject.toml and src/atlas_agent/__init__.py versions differ",
                )
            )
        checks["expected_source_version"] = source_version == RELEASE_METADATA.expected_source_version
        if not checks["expected_source_version"]:
            findings.append(
                _finding(
                    "source_version_unexpected",
                    "source package version is "
                    f"{source_version or 'unknown'}, expected {RELEASE_METADATA.expected_source_version}",
                )
            )

    metadata_findings = RELEASE_METADATA.validate(source_version, git_runner, repo_root)
    findings.extend(metadata_findings)

    if not (repo_root / "scripts" / "check_trust_center.py").exists():
        findings.append(
            _finding("trust_center_checker_missing", "trust center checker is missing")
        )
    checks["trust_center_checker_present"] = (
        repo_root / "scripts" / "check_trust_center.py"
    ).exists()
    if not (repo_root / "scripts" / "check_onboarding_docs.py").exists():
        findings.append(
            _finding("onboarding_checker_missing", "onboarding docs checker is missing")
        )
    checks["onboarding_checker_present"] = (
        repo_root / "scripts" / "check_onboarding_docs.py"
    ).exists()

    try:
        top_level_result = git_runner(repo_root, ["rev-parse", "--show-toplevel"])
        branch_result = git_runner(repo_root, ["branch", "--show-current"])
        head_result = git_runner(repo_root, ["rev-parse", "HEAD"])
        origin_result = git_runner(
            repo_root,
            ["rev-parse", "--verify", "origin/main^{commit}"],
        )
        status_result = git_runner(repo_root, ["status", "--porcelain=v1"])
        staged_result = git_runner(repo_root, ["diff", "--cached", "--name-only"])
        tag_result = git_runner(repo_root, ["tag", "--list", RELEASE_METADATA.next_unrequested_release_tag])
        protected_result = git_runner(
            repo_root,
            ["diff", "--name-status", "--", *PROTECTED_BOUNDARIES],
        )
    except FileNotFoundError:
        errors.append("git unavailable: executable not found")
        github = _collect_github_visibility(
            repo_root, include_github, gh_runner, warnings
        )
        return MainHealthReport(
            str(repo_root),
            source_version,
            RELEASE_METADATA.public_release,
            head_commit,
            origin_main_commit,
            checks,
            github,
            warnings,
            findings,
            errors,
        )
    except OSError as exc:
        errors.append(f"git unavailable: {_sanitize(str(exc))}")
        github = _collect_github_visibility(
            repo_root, include_github, gh_runner, warnings
        )
        return MainHealthReport(
            str(repo_root),
            source_version,
            RELEASE_METADATA.public_release,
            head_commit,
            origin_main_commit,
            checks,
            github,
            warnings,
            findings,
            errors,
        )

    git_results = {
        "git rev-parse --show-toplevel": top_level_result,
        "git branch --show-current": branch_result,
        "git rev-parse HEAD": head_result,
        "git status --porcelain=v1": status_result,
        "git diff --cached --name-only": staged_result,
        f"git tag --list {RELEASE_METADATA.next_unrequested_release_tag}": tag_result,
        "git diff --name-status protected boundaries": protected_result,
    }
    failed = [
        f"{name} failed with exit code {result.returncode}"
        for name, result in git_results.items()
        if result.returncode != 0
    ]
    if failed:
        errors.extend(failed)

    checks["git_available"] = not errors
    if top_level_result.returncode == 0:
        top_level = Path(top_level_result.stdout.strip()).resolve()
        checks["repo_root"] = top_level == repo_root
        if not checks["repo_root"]:
            findings.append(
                _finding(
                    "repo_root_mismatch",
                    f"git repository root is {top_level}, expected {repo_root}",
                )
            )

    if branch_result.returncode == 0:
        branch = branch_result.stdout.strip()
        checks["on_main"] = branch == "main"
        if not checks["on_main"]:
            findings.append(
                _finding("not_on_main", f"current branch is {branch or 'unknown'}, expected main")
            )

    if head_result.returncode == 0:
        head_commit = head_result.stdout.strip()
    if origin_result.returncode == 0:
        checks["origin_main_resolved"] = True
        origin_main_commit = origin_result.stdout.strip()
    else:
        findings.append(
            _finding(
                "origin_main_unresolved",
                "origin/main could not be resolved from local git metadata",
            )
        )

    if head_commit and origin_main_commit:
        checks["head_matches_origin_main"] = head_commit == origin_main_commit
        if not checks["head_matches_origin_main"]:
            findings.append(
                _finding(
                    "head_not_pushed",
                    "local HEAD does not match origin/main",
                )
            )

    if status_result.returncode == 0:
        status_paths = _parse_status(status_result.stdout)
        checks["working_tree_clean"] = not status_paths
        if status_paths:
            warnings.append(
                _finding(
                    "working_tree_dirty",
                    "working tree has local changes; resolve them before "
                    "treating main health as post-push complete",
                )
            )
        for status, path in status_paths:
            if status == "??" and _is_local_only_artifact(path):
                warnings.append(
                    _finding(
                        "untracked_local_generated_artifact",
                        "untracked generated artifact remains local: {path}",
                        path,
                    )
                )

    staged_paths: list[str] = []
    if staged_result.returncode == 0:
        staged_paths = _split_paths(staged_result.stdout)
        checks["no_staged_changes"] = not staged_paths
        if staged_paths:
            warnings.append(
                _finding(
                    "staged_changes_present",
                    "staged changes are present; post-push main health expects an empty index",
                )
            )

    staged_release_artifacts = [
        path for path in staged_paths if _is_release_publish_staged_artifact(path)
    ]
    checks["no_known_release_publish_artifacts_staged"] = not staged_release_artifacts
    for path in staged_release_artifacts:
        findings.append(
            _finding(
                "release_publish_artifact_staged",
                "release/publish artifact is staged without an explicit request: {path}",
                path,
            )
        )

    if tag_result.returncode == 0:
        tag_exists = bool(tag_result.stdout.strip())
        checks["no_unrequested_maintenance_tag"] = not tag_exists
        if tag_exists:
            findings.append(
                _finding(
                    "unrequested_maintenance_tag",
                    f"local future release tag {RELEASE_METADATA.next_unrequested_release_tag} exists but was not requested",
                )
            )

    if protected_result.returncode == 0:
        protected_diff = protected_result.stdout.strip()
        checks["protected_boundary_clean"] = not protected_diff
        if protected_diff:
            findings.append(
                _finding(
                    "protected_boundary_changed",
                    "protected runtime boundary diff is not empty for this docs/checker task",
                )
            )

    _collect_generated_artifact_hygiene(
        repo_root,
        git_runner,
        checks,
        warnings,
        findings,
        errors,
    )
    github = _collect_github_visibility(repo_root, include_github, gh_runner, warnings)

    return MainHealthReport(
        str(repo_root),
        source_version,
        RELEASE_METADATA.public_release,
        head_commit,
        origin_main_commit,
        checks,
        github,
        warnings,
        findings,
        errors,
    )


def _print_text(report: MainHealthReport) -> None:
    if report.errors:
        print("Main health report ERROR")
    elif report.findings:
        print("Main health report FAILED")
    elif report.warnings:
        print("Main health report PASSED with warnings")
    else:
        print("Main health report PASSED")

    print(f"  Repo root: {report.repo_root}")
    print(f"  Source version: {report.source_version or 'unknown'}")
    print(f"  Public release: {report.public_release}")
    print(f"  HEAD: {report.head_commit or 'unknown'}")
    print(f"  origin/main: {report.origin_main_commit or 'unknown'}")

    print("  Checks:")
    for name, ok in report.checks.items():
        status = "PASS" if ok else "FAIL"
        print(f"  - {name}: {status}")

    if report.github["requested"]:
        if report.github["gh_available"] is True:
            runs = report.github.get("runs", [])
            print(f"  GitHub CI visibility: {len(runs)} run line(s)")
            for line in runs:
                print(f"  - {line}")
        elif report.github["gh_available"] is False:
            print("  GitHub CI visibility: gh unavailable")
        else:
            print("  GitHub CI visibility: unknown")
    else:
        print("  GitHub CI visibility: not requested")

    if report.errors:
        print("  Operational errors:")
        for error in report.errors:
            print(f"  - {error}")

    if report.findings:
        print("  Blocking findings:")
        for finding in report.findings:
            print(f"  - {finding.detail}")
    else:
        print("  Blocking findings: 0")

    if report.warnings:
        print("  Warnings:")
        for warning in report.warnings:
            print(f"  - {warning.detail}")
    else:
        print("  Warnings: 0")


def main(
    argv: list[str] | None = None,
    *,
    git_runner: GitRunner = _run_git,
    gh_runner: GhRunner = _run_gh,
) -> int:
    parser = argparse.ArgumentParser(
        description="Report read-only direct-main post-push health."
    )
    parser.add_argument(
        "repo_root",
        nargs="?",
        default=Path(__file__).resolve().parent.parent,
        type=Path,
        help="Repository root to inspect. Defaults to this script's repository.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    parser.add_argument(
        "--include-github",
        action="store_true",
        help="Include optional GitHub CLI workflow run visibility.",
    )
    args = parser.parse_args(argv)

    report = collect_report(
        args.repo_root,
        include_github=args.include_github,
        git_runner=git_runner,
        gh_runner=gh_runner,
    )
    if args.json:
        print(json.dumps(report.to_jsonable(), indent=2, sort_keys=True))
    else:
        _print_text(report)
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
