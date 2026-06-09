#!/usr/bin/env python3
"""Validate generated artifact hygiene from git path metadata only."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


LOCAL_ONLY_ARTIFACT_PREFIXES = (
    "artifacts/release_evidence/",
    "artifacts/release_assurance/",
    "artifacts/provider_audit_pack/",
    "artifacts/provider_preflight/",
    "artifacts/provider_preflight_bundles/",
    "artifacts/provider_preflight_smoke/",
)

TRACKED_VERSIONED_EVIDENCE_PREFIXES = (
    "artifacts/release_assurance/v0.5.9/",
    "artifacts/release_assurance/v0.5.9-local-check/",
    "artifacts/release_assurance/v0.5.9.5/",
    "artifacts/release_assurance/v0.5.9.5-local-check/",
    "artifacts/release_assurance/v0.6.0/",
    "artifacts/release_assurance/v0.6.0-local-check/",
    "artifacts/release_assurance/v0.6.6/",
    "artifacts/release_assurance/v0.6.6-local-check/",
)

SECRET_TEMPLATE_ALLOWLIST = {
    ".env.example",
    "src/atlas_agent/templates/routine-trader/.env.example",
    "templates/routine-trader/.env.example",
}

SECRET_EXACT_BASENAMES = {
    ".env",
    ".env.atlas",
    "id_rsa",
    "id_ed25519",
}

SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".secret")
DANGEROUS_ARTIFACT_SUFFIXES = (
    ".env",
    ".key",
    ".pem",
    ".p12",
    ".pfx",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".log",
    ".jsonl",
    ".zip",
    ".tar",
    ".tgz",
    ".gz",
)

SECRET_NAME_RE = re.compile(
    r"(^|[._-])(?:api[._-]?key|token|password)(?:$|[._-])",
    re.IGNORECASE,
)

SECRET_VALUE_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9][A-Za-z0-9_-]{8,}"),
    re.compile(
        r"(?i)((?:api[._-]?key|token|password|secret)[^/]{0,12}[=:_-])"
        r"[A-Za-z0-9._~+=-]{8,}"
    ),
)


@dataclass(frozen=True)
class GitResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    detail: str

    def to_jsonable(self) -> dict[str, str]:
        return {
            "code": self.code,
            "detail": self.detail,
            "path": self.path,
        }


@dataclass(frozen=True)
class HygieneReport:
    repo_root: str
    checks: dict[str, bool]
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
            "artifact_type": "atlas_generated_artifact_hygiene_report",
            "schema_version": 1,
            "valid": self.valid,
            "checks": self.checks,
            "warnings": [warning.to_jsonable() for warning in self.warnings],
            "findings": [finding.to_jsonable() for finding in self.findings],
            "errors": self.errors,
            "repo_root": self.repo_root,
        }


GitRunner = Callable[[Path, list[str]], GitResult]


def _run_git(repo_root: Path, args: list[str]) -> GitResult:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return GitResult(result.returncode, result.stdout, result.stderr)


def _split_paths(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip()]


def _parse_status_paths(output: str) -> list[tuple[str, str]]:
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


def _is_tracked_versioned_evidence(path: str) -> bool:
    return _is_under(path, TRACKED_VERSIONED_EVIDENCE_PREFIXES)


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _is_secret_like_path(path: str) -> bool:
    if path in SECRET_TEMPLATE_ALLOWLIST:
        return False
    base = _basename(path)
    lower_base = base.lower()
    if base in SECRET_EXACT_BASENAMES:
        return True
    if lower_base.startswith(".env.") and lower_base != ".env.example":
        return True
    if lower_base.endswith(SECRET_SUFFIXES):
        return True
    if SECRET_NAME_RE.search(base):
        return True
    if re.search(r"_(?:TOKEN|PASSWORD|SECRET)(?:$|\.)", base):
        return True
    return False


def _is_dangerous_artifact_path(path: str) -> bool:
    return path.startswith("artifacts/") and path.lower().endswith(
        DANGEROUS_ARTIFACT_SUFFIXES
    )


def _sanitize_path(path: str) -> str:
    sanitized = path
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


def _finding(code: str, path: str, detail: str) -> Finding:
    safe_path = _sanitize_path(path)
    return Finding(code=code, path=safe_path, detail=detail.format(path=safe_path))


def _dedupe(findings: Iterable[Finding]) -> list[Finding]:
    seen: set[tuple[str, str]] = set()
    deduped: list[Finding] = []
    for finding in findings:
        key = (finding.code, finding.path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)
    return deduped


def collect_report(repo_root: Path, git_runner: GitRunner = _run_git) -> HygieneReport:
    repo_root = repo_root.resolve()
    checks = {
        "git_available": False,
        "no_tracked_local_evidence_artifacts": False,
        "no_staged_local_evidence_artifacts": False,
        "no_tracked_secret_like_files": False,
        "no_staged_secret_like_files": False,
        "no_staged_dangerous_artifact_file_types": False,
    }
    errors: list[str] = []

    try:
        status_result = git_runner(repo_root, ["status", "--porcelain=v1"])
        tracked_result = git_runner(repo_root, ["ls-files"])
        staged_result = git_runner(repo_root, ["diff", "--cached", "--name-only"])
    except FileNotFoundError:
        errors.append("git unavailable: executable not found")
        return HygieneReport(str(repo_root), checks, [], [], errors)
    except OSError as exc:
        errors.append(f"git unavailable: {exc}")
        return HygieneReport(str(repo_root), checks, [], [], errors)

    git_results = {
        "git status --porcelain=v1": status_result,
        "git ls-files": tracked_result,
        "git diff --cached --name-only": staged_result,
    }
    failed = [
        f"{name} failed with exit code {result.returncode}"
        for name, result in git_results.items()
        if result.returncode != 0
    ]
    if failed:
        errors.extend(failed)
        return HygieneReport(str(repo_root), checks, [], [], errors)

    checks["git_available"] = True
    tracked_paths = _split_paths(tracked_result.stdout)
    staged_paths = _split_paths(staged_result.stdout)
    status_paths = _parse_status_paths(status_result.stdout)

    tracked_local = [
        path
        for path in tracked_paths
        if _is_local_only_artifact(path) and not _is_tracked_versioned_evidence(path)
    ]
    staged_local = [path for path in staged_paths if _is_local_only_artifact(path)]
    tracked_secrets = [path for path in tracked_paths if _is_secret_like_path(path)]
    staged_secrets = [path for path in staged_paths if _is_secret_like_path(path)]
    staged_dangerous_artifacts = [
        path for path in staged_paths if _is_dangerous_artifact_path(path)
    ]
    untracked_local = [
        path
        for status, path in status_paths
        if status == "??" and _is_local_only_artifact(path)
    ]

    checks["no_tracked_local_evidence_artifacts"] = not tracked_local
    checks["no_staged_local_evidence_artifacts"] = not staged_local
    checks["no_tracked_secret_like_files"] = not tracked_secrets
    checks["no_staged_secret_like_files"] = not staged_secrets
    checks["no_staged_dangerous_artifact_file_types"] = not staged_dangerous_artifacts

    findings = _dedupe(
        [
            *[
                _finding(
                    "tracked_local_evidence_artifact",
                    path,
                    "tracked local-only generated evidence artifact: {path}",
                )
                for path in tracked_local
            ],
            *[
                _finding(
                    "staged_local_evidence_artifact",
                    path,
                    "staged local-only generated evidence artifact: {path}",
                )
                for path in staged_local
            ],
            *[
                _finding(
                    "tracked_secret_like_file",
                    path,
                    "tracked secret-like filename: {path}",
                )
                for path in tracked_secrets
            ],
            *[
                _finding(
                    "staged_secret_like_file",
                    path,
                    "staged secret-like filename: {path}",
                )
                for path in staged_secrets
            ],
            *[
                _finding(
                    "staged_dangerous_artifact_file_type",
                    path,
                    "staged dangerous generated artifact file type: {path}",
                )
                for path in staged_dangerous_artifacts
            ],
        ]
    )
    warnings = _dedupe(
        [
            _finding(
                "untracked_local_evidence_artifact",
                path,
                "untracked local-only generated evidence artifact remains local: {path}",
            )
            for path in untracked_local
        ]
    )

    return HygieneReport(str(repo_root), checks, warnings, findings, errors)


def _print_cleanup_guidance(warnings: list[Finding]) -> None:
    untracked = [
        w for w in warnings if w.code == "untracked_local_evidence_artifact"
    ]
    if not untracked:
        return

    print("  Safe cleanup guidance (review each path before running):")
    print("    mkdir -p /tmp/atlas-agent-artifact-backup")
    for warning in untracked:
        if _is_local_only_artifact(warning.path):
            print(f"    mv {warning.path} /tmp/atlas-agent-artifact-backup/")
    print("    # Do not use git clean, git reset --hard, stash pop, or stash drop.")


def _print_text(report: HygieneReport) -> None:
    if report.errors:
        print("Generated artifact hygiene check ERROR")
    elif report.findings:
        print("Generated artifact hygiene check FAILED")
    else:
        print("Generated artifact hygiene check PASSED")

    print(f"  Repo root: {report.repo_root}")

    if report.errors:
        print("  Operational errors:")
        for error in report.errors:
            print(f"  - {error}")
        return

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
        _print_cleanup_guidance(report.warnings)
    else:
        print("  Warnings: 0")


def main(argv: list[str] | None = None, git_runner: GitRunner = _run_git) -> int:
    parser = argparse.ArgumentParser(
        description="Check generated artifact hygiene without modifying files."
    )
    parser.add_argument(
        "repo_root",
        nargs="?",
        default=Path(__file__).resolve().parent.parent,
        type=Path,
        help="Repository root to inspect. Defaults to this script's repository.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    report = collect_report(args.repo_root, git_runner=git_runner)
    if args.json:
        print(json.dumps(report.to_jsonable(), indent=2, sort_keys=True))
    else:
        _print_text(report)
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
