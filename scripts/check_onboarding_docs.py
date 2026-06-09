#!/usr/bin/env python3
"""Validate contributor onboarding docs.

The check is deterministic and local. It does not install dependencies, load
credentials, call providers, contact brokers, create tags, publish packages, or
modify runtime state.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ONBOARDING_DOC = Path("docs/development/onboarding.md")
SAFE_WORKFLOWS_DOC = Path("docs/development/safe-local-workflows.md")
CHECKS_REFERENCE_DOC = Path("docs/development/checks-reference.md")
GENERATED_ARTIFACTS_DOC = Path("docs/development/generated-artifacts.md")
MAIN_HEALTH_DOC = Path("docs/development/main-health.md")
GITHUB_ACTIONS_DOC = Path("docs/development/github-actions.md")

CURRENT_PACKAGE_VERSION = "0.6.6"
CURRENT_PUBLIC_RELEASE = "v0.6.6"
NEXT_PLANNED_RELEASE = "v0.6.7"

REQUIRED_DOCS = [
    ONBOARDING_DOC,
    SAFE_WORKFLOWS_DOC,
    CHECKS_REFERENCE_DOC,
    GENERATED_ARTIFACTS_DOC,
    MAIN_HEALTH_DOC,
    GITHUB_ACTIONS_DOC,
]

REQUIRED_SECTIONS = {
    ONBOARDING_DOC: [
        "Requirements",
        "Clone and Environment Setup",
        "Install Dev Dependencies",
        "First Sanity Checks",
        "Safe Local Commands",
        "Evidence and Assurance Commands",
        "Git Workflow",
        "Pull Request Checklist",
        "Common Failure Modes",
        "Safety Rules",
    ],
    SAFE_WORKFLOWS_DOC: [
        "Safe By Default",
        "Paper-Only / Dry-Run Commands",
        "Provider Evidence Commands",
        "Release Assurance Commands",
        "Commands Requiring Explicit Owner Approval",
        "Commands Not Allowed During Normal Development",
        "Handling Dirty Worktrees",
        "Handling Generated Artifacts",
        "Handling Secrets",
        "Troubleshooting Permission/Approval Timeouts",
    ],
    CHECKS_REFERENCE_DOC: [
        "Core Checks",
        "Development Checks",
        "CI Checks",
        "Release Checks",
        "Research Checks",
        "Trust Center Checks",
        "Provider Audit Checks",
        "Release Assurance Checks",
        "Protected Boundary Checks",
        "Dangerous Pattern Scans",
        "Interpreting Failures",
    ],
    GENERATED_ARTIFACTS_DOC: [
        "Purpose",
        "Local-Only Evidence Outputs",
        "Versioned Evidence Exceptions",
        "What Not To Commit",
        "How To Check Artifact Hygiene",
        "How To Handle Untracked Local Artifacts",
        "Safe Cleanup Without Destructive Git Commands",
        "CI and Local Gates",
    ],
    MAIN_HEALTH_DOC: [
        "Purpose",
        "When To Run",
        "Local-Only Checks",
        "Optional GitHub CI Visibility",
        "Expected Direct-Main State",
        "Version and Release Identity",
        "Artifact Hygiene",
        "Protected Runtime Boundaries",
        "Interpreting Findings",
        "Safe Follow-Up Actions",
    ],
    GITHUB_ACTIONS_DOC: [
        "Purpose",
        "Current Action Version Policy",
        "Node 24 Compatibility",
        "Workflow Safety Rules",
        "Manual Verification",
        "What Not To Change",
    ],
}

REQUIRED_FACTS = {
    "Python 3.11": (("python 3.11",), ("python3.11",)),
    "dev extras install": (('python -m pip install -e ".[dev]"',), ("dev extras", ".[dev]")),
    "no real credentials required": (("no real credentials required",),),
    "live trading disabled by default": (("live trading is disabled by default",),),
    "provider execution disabled by default": (
        ("provider execution is disabled by default",),
    ),
    "check_version_consistency": (("check_version_consistency.py",),),
    "check_forbidden_claims": (("check_forbidden_claims.py",),),
    "check_trust_center": (("check_trust_center.py",),),
    "check_generated_artifacts": (("check_generated_artifacts.py",),),
    "main health report": (("main_health.py",),),
    "GitHub Actions version check": (("check_github_actions_versions.py",),),
    "GitHub Actions checkout v6": (("actions/checkout@v6",),),
    "GitHub Actions setup-python v6": (("actions/setup-python@v6",),),
    "GitHub Actions upload-artifact v6": (("actions/upload-artifact@v6",),),
    "GitHub Actions Node 24 compatibility": (("node 24", "ubuntu-latest"),),
    "self-hosted runner requirement": (("self-hosted", "v2.327.1+"),),
    "dev_check.sh": (("dev_check.sh",),),
    "ci_check.sh": (("ci_check.sh",),),
    "release_check.sh --quick": (("release_check.sh --quick",),),
    "release_assurance.py": (("release_assurance.py",),),
    "provider audit-pack": (("providers audit-pack",), ("provider audit-pack",)),
    "verify-audit-pack": (("providers verify-audit-pack",), ("verify-audit-pack",)),
    "update check --dry-run": (("update check --dry-run",),),
    "protected-boundary check": (
        ("git diff --name-status --", "src/atlas_agent/config", "src/atlas_agent/risk"),
    ),
    "dangerous-pattern scan": (
        ("git diff | grep -n -e",),
        ("git diff | grep -n -E", "twine|pypi|gh release"),
    ),
    "generated artifacts guidance": (
        ("artifacts/ outputs are usually local evidence",),
        ("only commit artifacts when the task explicitly requires",),
    ),
    "main health version identity": (
        ("main source version can differ from public release",),
        (f"public github release is `{CURRENT_PUBLIC_RELEASE}`",),
    ),
    "main health protected boundary": (
        ("protected runtime boundaries should be empty for docs/checker-only work",),
    ),
}

SECRET_PATTERNS = [
    ("OpenAI-style secret key", re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{12,}\b")),
    ("Alpaca-style key", re.compile(r"\bAPCA-[A-Z0-9]{10,}\b")),
    ("bearer credential", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}", re.I)),
    (
        "assigned credential value",
        re.compile(
            r"\b(?:api[_-]?key|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{12,}",
            re.I,
        ),
    ),
]

DESTRUCTIVE_PATTERNS = [
    ("git reset --hard", re.compile(r"\bgit\s+reset\s+--hard\b", re.I)),
    ("git clean", re.compile(r"\bgit\s+clean\b", re.I)),
    ("stash pop", re.compile(r"\bstash\s+pop\b", re.I)),
    ("stash drop", re.compile(r"\bstash\s+drop\b", re.I)),
    ("stash clear", re.compile(r"\bstash\s+clear\b", re.I)),
]

RELEASE_SENSITIVE_PATTERNS = [
    ("git tag", re.compile(r"\bgit\s+tag\b", re.I)),
    ("gh release create", re.compile(r"\bgh\s+release\s+create\b", re.I)),
    ("PyPI publish", re.compile(r"\bpypi\s+publish\b|\bpublish(?:ing)?\s+to\s+pypi\b", re.I)),
    ("twine", re.compile(r"\btwine\b", re.I)),
]

WARNING_WORDS = (
    "do not",
    "not allowed",
    "warning",
    "warnings",
    "requires explicit owner approval",
    "explicit owner approval",
    "outside warning context",
    "must not",
    "not a publishing workflow",
)

SAFE_COMMAND_SECTIONS = {
    "Commands Requiring Explicit Owner Approval",
    "Commands Not Allowed During Normal Development",
    "Handling Dirty Worktrees",
    "Troubleshooting Permission/Approval Timeouts",
    "Safety Rules",
    "Dangerous Pattern Scans",
    "Interpreting Failures",
    "What Not To Commit",
    "How To Handle Untracked Local Artifacts",
    "Safe Cleanup Without Destructive Git Commands",
    "CI and Local Gates",
    "Optional GitHub CI Visibility",
    "Expected Direct-Main State",
    "Version and Release Identity",
    "Interpreting Findings",
    "Safe Follow-Up Actions",
    "Workflow Safety Rules",
    "What Not To Change",
}


@dataclass(frozen=True)
class Check:
    id: str
    status: str
    detail: str


@dataclass(frozen=True)
class ValidationResult:
    repo_root: str
    checks: list[Check]
    findings: list[str]
    errors: list[str]

    @property
    def exit_code(self) -> int:
        if self.errors:
            return 2
        if self.findings:
            return 1
        return 0

    @property
    def status(self) -> str:
        if self.errors:
            return "error"
        if self.findings:
            return "failed"
        return "passed"

    def to_jsonable(self) -> dict[str, object]:
        return {
            "artifact_type": "atlas_onboarding_docs_check",
            "schema_version": 1,
            "valid": self.exit_code == 0,
            "checks": [check.__dict__ for check in self.checks],
            "errors": self.errors,
            "exit_code": self.exit_code,
            "findings": self.findings,
            "repo_root": self.repo_root,
            "status": self.status,
        }


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _line_no(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _add_check(
    checks: list[Check],
    findings: list[str],
    check_id: str,
    ok: bool,
    pass_detail: str,
    fail_detail: str,
) -> None:
    if ok:
        checks.append(Check(check_id, "pass", pass_detail))
        return
    checks.append(Check(check_id, "fail", fail_detail))
    findings.append(fail_detail)


def _contains_any_fact(compact_text: str, variants: Iterable[tuple[str, ...]]) -> bool:
    for terms in variants:
        if all(term.lower() in compact_text for term in terms):
            return True
    return False


def _current_sections(text: str) -> list[tuple[int, str]]:
    sections: list[tuple[int, str]] = []
    current = ""
    for lineno, line in enumerate(text.splitlines(), start=1):
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            current = match.group(1)
        sections.append((lineno, current))
    return sections


def _section_at(sections: list[tuple[int, str]], lineno: int) -> str:
    if lineno <= 0 or lineno > len(sections):
        return ""
    return sections[lineno - 1][1]


def _is_warning_context(line: str, section: str) -> bool:
    lower = line.lower()
    return section in SAFE_COMMAND_SECTIONS or any(word in lower for word in WARNING_WORDS)


def _validate_required_sections(
    *,
    checks: list[Check],
    findings: list[str],
    rel_path: Path,
    text: str,
    sections: list[str],
) -> None:
    for section in sections:
        heading = f"## {section}"
        _add_check(
            checks,
            findings,
            f"{rel_path}:{section}",
            heading in text,
            f"{rel_path} contains section '{section}'",
            f"{rel_path} is missing required section '{section}'",
        )


def _validate_secret_patterns(
    *,
    checks: list[Check],
    findings: list[str],
    docs: dict[Path, str],
) -> None:
    secret_findings: list[str] = []
    for rel_path, text in docs.items():
        for label, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                secret_findings.append(
                    f"{rel_path}:{_line_no(text, match.start())}: secret-like value matched ({label})"
                )
    _add_check(
        checks,
        findings,
        "secret-like-scan",
        not secret_findings,
        "onboarding docs do not contain raw secret-like values",
        "; ".join(secret_findings),
    )


def _validate_sensitive_commands(
    *,
    checks: list[Check],
    findings: list[str],
    docs: dict[Path, str],
) -> None:
    command_findings: list[str] = []
    for rel_path, text in docs.items():
        sections = _current_sections(text)
        patterns = DESTRUCTIVE_PATTERNS + RELEASE_SENSITIVE_PATTERNS
        for label, pattern in patterns:
            for match in pattern.finditer(text):
                lineno = _line_no(text, match.start())
                line = text.splitlines()[lineno - 1].strip()
                section = _section_at(sections, lineno)
                if not _is_warning_context(line, section):
                    command_findings.append(
                        f"{rel_path}:{lineno}: {label} appears outside warning/approval context"
                    )
    _add_check(
        checks,
        findings,
        "sensitive-command-context",
        not command_findings,
        "destructive and release-sensitive commands appear only in warning/approval context",
        "; ".join(command_findings),
    )


def validate_onboarding_docs(repo_root: Path) -> ValidationResult:
    repo_root = repo_root.resolve()
    checks: list[Check] = []
    findings: list[str] = []
    errors: list[str] = []

    if not repo_root.exists():
        return ValidationResult(
            repo_root=str(repo_root),
            checks=[],
            findings=[],
            errors=[f"repo root does not exist: {repo_root}"],
        )

    docs: dict[Path, str] = {}
    for rel_path in REQUIRED_DOCS:
        path = repo_root / rel_path
        exists = path.exists()
        _add_check(
            checks,
            findings,
            f"exists:{rel_path}",
            exists,
            f"{rel_path} exists",
            f"{rel_path} is missing",
        )
        if exists:
            try:
                docs[rel_path] = _read_text(path)
            except OSError as exc:
                errors.append(f"could not read {rel_path}: {exc}")

    for rel_path, sections in REQUIRED_SECTIONS.items():
        text = docs.get(rel_path, "")
        if text:
            _validate_required_sections(
                checks=checks,
                findings=findings,
                rel_path=rel_path,
                text=text,
                sections=sections,
            )

    combined_text = "\n\n".join(docs.values())
    compact = _compact(combined_text)
    for fact, variants in REQUIRED_FACTS.items():
        _add_check(
            checks,
            findings,
            f"fact:{fact}",
            _contains_any_fact(compact, variants),
            f"onboarding docs mention {fact}",
            f"onboarding docs do not mention {fact}",
        )

    _validate_sensitive_commands(checks=checks, findings=findings, docs=docs)
    _validate_secret_patterns(checks=checks, findings=findings, docs=docs)

    return ValidationResult(
        repo_root=str(repo_root),
        checks=checks,
        findings=findings,
        errors=errors,
    )


def _print_text_result(result: ValidationResult) -> None:
    if result.status == "passed":
        print("Onboarding docs check PASSED")
    elif result.status == "failed":
        print("Onboarding docs check FAILED")
    else:
        print("Onboarding docs check ERROR")

    print(f"  Repo root: {result.repo_root}")
    print(f"  Checks: {len(result.checks)}")

    if result.errors:
        print("  Operational errors:")
        for error in result.errors:
            print(f"  - {error}")
        return

    if result.findings:
        print("  Blocking findings:")
        for finding in result.findings:
            print(f"  - {finding}")
        return

    print("  Blocking findings: 0")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Atlas Agent onboarding docs.")
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

    result = validate_onboarding_docs(args.repo_root)
    if args.json:
        print(json.dumps(result.to_jsonable(), indent=2, sort_keys=True))
    else:
        _print_text_result(result)
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
