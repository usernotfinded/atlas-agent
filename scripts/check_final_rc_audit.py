#!/usr/bin/env python3
"""Static/local final audit check for the RC series before stable release.

Deterministic and local. Does not:
- call network
- call GitHub API
- publish
- upload
- tag
- push
- require credentials
- run live trading
- call brokers/providers
- use shell = True
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

CURRENT_PACKAGE_VERSION = "0.6.8"
HISTORICAL_STABLE_TAG = "v0.5.8"

REQUIRED_FILES = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "SECURITY.md",
    REPO_ROOT / "CONTRIBUTING.md",
    REPO_ROOT / "CHANGELOG.md",
    REPO_ROOT / "docs" / "final-rc-audit.md",
    REPO_ROOT / "docs" / "final-release-candidate-checklist.md",
    REPO_ROOT / "docs" / "releases" / f"{HISTORICAL_STABLE_TAG}.md",
    REPO_ROOT / "docs" / "public-launch-readiness.md",
    REPO_ROOT / "docs" / "external-reviewer-walkthrough.md",
    REPO_ROOT / "docs" / "reviewer-checklist.md",
    REPO_ROOT / "docs" / "public-launch-messaging.md",
    REPO_ROOT / "docs" / "feedback-request-guide.md",
    REPO_ROOT / "docs" / "public-faq.md",
    REPO_ROOT / "docs" / "release-checklist.md",
    REPO_ROOT / "docs" / "ci-release-gates.md",
    REPO_ROOT / "docs" / "clean-install-verification.md",
    REPO_ROOT / "docs" / "package-distribution-verification.md",
    REPO_ROOT / ".github" / "pull_request_template.md",
    REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml",
    REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "docs_issue.yml",
    REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "safety_concern.yml",
    REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml",
]

PUBLIC_DOC_PATHS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "SECURITY.md",
    REPO_ROOT / "CONTRIBUTING.md",
    REPO_ROOT / "docs" / "final-rc-audit.md",
    REPO_ROOT / "docs" / "final-release-candidate-checklist.md",
    REPO_ROOT / "docs" / "public-launch-readiness.md",
    REPO_ROOT / "docs" / "external-reviewer-walkthrough.md",
    REPO_ROOT / "docs" / "reviewer-checklist.md",
    REPO_ROOT / "docs" / "public-launch-messaging.md",
    REPO_ROOT / "docs" / "feedback-request-guide.md",
    REPO_ROOT / "docs" / "public-faq.md",
    REPO_ROOT / "docs" / "release-checklist.md",
]

# Forbidden positive claims about live trading / provider execution.
_FORBIDDEN_POSITIVE_CLAIMS = [
    "live trading ready",
    "production trading ready",
    "safe to trade",
    "trust granted",
    "provider execution enabled",
    "broker execution enabled",
    "orders enabled",
    "approvals enabled",
    "autonomous trading ready",
    "real-money ready",
    "guaranteed profit",
    "profitable strategy",
    "verified alpha",
    "beats the market",
]

# Secret-like patterns.
_SECRET_PATTERNS = [
    r"\bsk-[A-Za-z0-9]{10,}",
    r"\bAPCA-[A-Z0-9]{10,}",
    r"\bBearer\s+[A-Za-z0-9._~+/=-]{10,}",
    r"\bAuthorization:\s*Bearer\s+[A-Za-z0-9._~+/=-]+",
]

# Absolute path prefixes that must not appear in output or docs.
_ABSOLUTE_PATH_PREFIXES = [
    "/Users/",
    "/private/var/",
    "/var/folders/",
    "/tmp/",
    "/var/tmp/",
]


def _redact(text: str) -> str:
    """Redact user-specific absolute paths from output."""
    home = str(Path.home())
    repo = str(REPO_ROOT)
    replacements = [
        (home, "~"),
        (repo, "<repo>"),
        ("/Users/", "<home>/"),
        ("/private/var/", "<temp>/"),
        ("/var/folders/", "<temp>/"),
        ("/tmp/", "<temp>/"),
        ("/var/tmp/", "<temp>/"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _read(path: Path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _check_required_files() -> list[str]:
    errors: list[str] = []
    for path in REQUIRED_FILES:
        if not path.exists():
            rel = path.relative_to(REPO_ROOT)
            errors.append(f"Required file missing: {rel}")
    return errors


def _check_readme_links() -> list[str]:
    errors: list[str] = []
    readme = REPO_ROOT / "README.md"
    text = _read(readme)
    lower = text.lower()

    if "final-rc-audit.md" not in text and "final rc audit" not in lower:
        errors.append("README.md missing link to final RC audit")

    if "final-release-candidate-checklist.md" not in text and "final release candidate checklist" not in lower:
        errors.append("README.md missing link to final release candidate checklist")

    if "public-launch-readiness.md" not in text and "public launch readiness" not in lower:
        errors.append("README.md missing link to public launch readiness")

    if "external-reviewer-walkthrough.md" not in text and "reviewer walkthrough" not in lower:
        errors.append("README.md missing link to reviewer walkthrough")

    if "public-faq.md" not in text and "public faq" not in lower:
        errors.append("README.md missing link to public FAQ")

    if HISTORICAL_STABLE_TAG not in text and CURRENT_PACKAGE_VERSION not in text:
        errors.append("README.md missing version status reference")

    return errors


def _check_public_docs_safety() -> list[str]:
    errors: list[str] = []
    for path in PUBLIC_DOC_PATHS:
        if not path.exists():
            continue
        text = _read(path)
        lower = text.lower()
        rel = str(path.relative_to(REPO_ROOT))

        for claim in _FORBIDDEN_POSITIVE_CLAIMS:
            if claim in lower:
                idx = lower.index(claim)
                context_start = max(0, idx - 120)
                context_end = min(len(lower), idx + 120)
                context = lower[context_start:context_end]
                negative_indicators = (
                    "not ", "does not", "never", "no ", "avoid",
                    "disclaimer", "prohibited", "forbidden", "must not",
                    "cannot", "do not", "is not", "are not", "without",
                    "fail closed", "not yet", "not implemented", "not enabled",
                    "not authorized", "not a ", "not ready", "remains disabled",
                    "remains locked", "remains blocked", "do not assume",
                )
                if not any(ind in context for ind in negative_indicators):
                    errors.append(f"[{rel}] Forbidden claim: {claim}")

        for prefix in _ABSOLUTE_PATH_PREFIXES:
            if prefix in text:
                errors.append(f"[{rel}] Absolute path fragment: {prefix}")

        for pattern in _SECRET_PATTERNS:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                errors.append(f"[{rel}] Secret-like pattern: {m.group(0)[:40]}")

    return errors


def _check_changelog_entry() -> list[str]:
    errors: list[str] = []
    changelog = REPO_ROOT / "CHANGELOG.md"
    if changelog.exists():
        text = changelog.read_text(encoding="utf-8")
        if f"[{CURRENT_PACKAGE_VERSION}]" not in text and "[Unreleased]" not in text and f"[{HISTORICAL_STABLE_TAG.lstrip('v')}]" not in text:
            errors.append(f"CHANGELOG.md missing entry for [{CURRENT_PACKAGE_VERSION}] or [Unreleased] or [{HISTORICAL_STABLE_TAG.lstrip('v')}]")
    else:
        errors.append("CHANGELOG.md not found")
    return errors


def _check_version_match() -> list[str]:
    errors: list[str] = []
    pyproject = REPO_ROOT / "pyproject.toml"
    init = REPO_ROOT / "src" / "atlas_agent" / "__init__.py"

    import tomllib
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    toml_version = data.get("project", {}).get("version")
    if toml_version != CURRENT_PACKAGE_VERSION:
        errors.append(f"pyproject.toml version {toml_version} != {CURRENT_PACKAGE_VERSION}")

    init_text = init.read_text(encoding="utf-8")
    m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', init_text, re.MULTILINE)
    init_version = m.group(1) if m else None
    if init_version != CURRENT_PACKAGE_VERSION:
        errors.append(f"__init__.py version {init_version} != {CURRENT_PACKAGE_VERSION}")

    return errors


def _check_no_staged_artifacts() -> list[str]:
    errors: list[str] = []
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    staged = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    forbidden = ("dist/", "build/")
    for f in staged:
        if f.startswith(forbidden) or f.endswith(".egg-info/"):
            errors.append(f"Package artifact staged: {f}")
    return errors


def _check_checklist_has_boundary_commands() -> list[str]:
    errors: list[str] = []
    checklist = REPO_ROOT / "docs" / "final-release-candidate-checklist.md"
    if checklist.exists():
        text = checklist.read_text(encoding="utf-8").lower()
        if "git diff -- src/atlas_agent/config" not in text:
            errors.append("Final checklist missing protected boundary diff command")
        if "release_check.sh --full" not in text:
            errors.append("Final checklist missing release_check.sh --full command")
    return errors


def _run_checks() -> dict:
    all_errors: list[str] = []
    all_errors.extend(_check_required_files())
    all_errors.extend(_check_readme_links())
    all_errors.extend(_check_public_docs_safety())
    all_errors.extend(_check_changelog_entry())
    all_errors.extend(_check_version_match())
    all_errors.extend(_check_no_staged_artifacts())
    all_errors.extend(_check_checklist_has_boundary_commands())

    result = {
        "passed": len(all_errors) == 0,
        "package_version": CURRENT_PACKAGE_VERSION,
        "public_tag": HISTORICAL_STABLE_TAG,
        "errors": all_errors,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Final RC audit check for Atlas Agent."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON (redacted).",
    )
    args = parser.parse_args()

    result = _run_checks()

    if args.json:
        redacted_errors = [_redact(e) for e in result["errors"]]
        output = {
            "passed": result["passed"],
            "package_version": result["package_version"],
            "public_tag": result["public_tag"],
            "errors": redacted_errors,
        }
        print(json.dumps(output, indent=2))
        return 0 if result["passed"] else 2

    if result["errors"]:
        print("Final RC audit check FAILED")
        for e in result["errors"]:
            print(f"  - {_redact(e)}")
        return 2

    print("Final RC audit check PASSED")
    print(f"  Current package version: {result['package_version']}")
    print(f"  Historical stable tag: {result['public_tag']}")
    print(f"  Required files: {len(REQUIRED_FILES)} present")
    print(f"  Public docs safe: yes")
    print(f"  No staged artifacts: yes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
