#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/check_github_actions_versions.py
# PURPOSE: Validate GitHub Actions workflow action majors for Node 24
#         compatibility.
# DEPS:    argparse, json, re, sys, dataclasses, pathlib.
# ==============================================================================

"""Validate GitHub Actions workflow action majors for Node 24 compatibility."""

# --- IMPORTS ---

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


# --- CONFIGURATION AND CONSTANTS ---

ACTION_VERSION_POLICY = {
    "actions/checkout": "v6",
    "actions/setup-python": "v6",
    "actions/upload-artifact": "v6",
}

WORKFLOW_GLOBS = ("*.yml", "*.yaml")
ACTION_RE = re.compile(
    r"(?P<action>actions/(?:checkout|setup-python|upload-artifact))@(?P<version>[A-Za-z0-9._-]+)"
)


# ==============================================================================
# VALIDATION WORKFLOW
# ==============================================================================

# --- VALIDATION HELPERS AND ENTRYPOINTS ---

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
class WorkflowActionReport:
    repo_root: str
    workflow_files: list[str]
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
            "artifact_type": "atlas_github_actions_version_report",
            "schema_version": 1,
            "valid": self.valid,
            "repo_root": self.repo_root,
            "workflow_files": self.workflow_files,
            "checks": self.checks,
            "warnings": [warning.to_jsonable() for warning in self.warnings],
            "findings": [finding.to_jsonable() for finding in self.findings],
            "errors": self.errors,
        }


def _workflow_files(repo_root: Path) -> list[Path]:
    workflow_dir = repo_root / ".github" / "workflows"
    files: list[Path] = []
    for pattern in WORKFLOW_GLOBS:
        files.extend(workflow_dir.glob(pattern))
    return sorted(path for path in files if path.is_file())


def _rel(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def collect_report(repo_root: Path) -> WorkflowActionReport:
    repo_root = repo_root.resolve()
    workflow_dir = repo_root / ".github" / "workflows"
    checks = {
        "workflow_files_present": False,
        "checkout_uses_v6": True,
        "setup_python_uses_v6": True,
        "upload_artifact_uses_v6": True,
        "no_deprecated_node20_action_majors": True,
    }
    warnings: list[Finding] = []
    findings: list[Finding] = []
    errors: list[str] = []

    if not workflow_dir.exists():
        errors.append(f"workflow directory missing: {_rel(workflow_dir, repo_root)}")
        return WorkflowActionReport(
            repo_root=str(repo_root),
            workflow_files=[],
            checks=checks,
            warnings=warnings,
            findings=findings,
            errors=errors,
        )

    files = _workflow_files(repo_root)
    checks["workflow_files_present"] = bool(files)
    if not files:
        errors.append("no GitHub Actions workflow files found")
        return WorkflowActionReport(
            repo_root=str(repo_root),
            workflow_files=[],
            checks=checks,
            warnings=warnings,
            findings=findings,
            errors=errors,
        )

    seen_actions: set[str] = set()
    for path in files:
        rel_path = _rel(path, repo_root)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"could not read {rel_path}: {exc}")
            continue

        for match in ACTION_RE.finditer(text):
            action = match.group("action")
            version = match.group("version")
            expected = ACTION_VERSION_POLICY[action]
            seen_actions.add(action)
            if version == expected:
                continue

            if action == "actions/checkout":
                checks["checkout_uses_v6"] = False
            elif action == "actions/setup-python":
                checks["setup_python_uses_v6"] = False
            elif action == "actions/upload-artifact":
                checks["upload_artifact_uses_v6"] = False
            checks["no_deprecated_node20_action_majors"] = False
            line_no = text.count("\n", 0, match.start()) + 1
            findings.append(
                Finding(
                    code="github_action_version_mismatch",
                    path=f"{rel_path}:{line_no}",
                    detail=f"{action} uses @{version}; expected @{expected}",
                )
            )

    for action, expected in ACTION_VERSION_POLICY.items():
        if action not in seen_actions:
            warnings.append(
                Finding(
                    code="github_action_not_used",
                    path=".github/workflows",
                    detail=f"{action} is not used by current workflow files; policy remains @{expected}",
                )
            )

    return WorkflowActionReport(
        repo_root=str(repo_root),
        workflow_files=[_rel(path, repo_root) for path in files],
        checks=checks,
        warnings=warnings,
        findings=findings,
        errors=errors,
    )


def _print_text_result(report: WorkflowActionReport) -> None:
    if report.errors:
        print("GitHub Actions version check ERROR")
    elif report.findings:
        print("GitHub Actions version check FAILED")
    else:
        print("GitHub Actions version check PASSED")

    print(f"  Repo root: {report.repo_root}")
    print(f"  Workflow files: {len(report.workflow_files)}")
    print("  Checks:")
    for name, ok in report.checks.items():
        print(f"  - {name}: {'PASS' if ok else 'FAIL'}")

    if report.errors:
        print("  Operational errors:")
        for error in report.errors:
            print(f"  - {error}")

    if report.findings:
        print("  Blocking findings:")
        for finding in report.findings:
            print(f"  - {finding.code}: {finding.path}: {finding.detail}")

    if report.warnings:
        print("  Warnings:")
        for warning in report.warnings:
            print(f"  - {warning.code}: {warning.path}: {warning.detail}")

    print(f"  Blocking findings: {len(report.findings)}")
    print(f"  Warnings: {len(report.warnings)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate GitHub Actions workflow action majors."
    )
    parser.add_argument(
        "repo_root",
        nargs="?",
        default=Path(__file__).resolve().parent.parent,
        type=Path,
        help="Repository root to validate. Defaults to this script's repository.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit deterministic JSON output.",
    )
    args = parser.parse_args(argv)

    report = collect_report(args.repo_root)
    if args.json:
        print(json.dumps(report.to_jsonable(), indent=2, sort_keys=True))
    else:
        _print_text_result(report)
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
