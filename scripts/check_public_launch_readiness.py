#!/usr/bin/env python3
"""Local static check that public-facing repo launch materials are present and safe.

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
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

PACKAGE_VERSION = "0.5.9.1"
PUBLIC_TAG = "v0.5.9"

REQUIRED_FILES = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "SECURITY.md",
    REPO_ROOT / "CONTRIBUTING.md",
    REPO_ROOT / "CHANGELOG.md",
    REPO_ROOT / "docs" / "public-launch-readiness.md",
    REPO_ROOT / "docs" / "github-repo-settings.md",
    REPO_ROOT / "docs" / "ci-release-gates.md",
    REPO_ROOT / "docs" / "package-distribution-verification.md",
    REPO_ROOT / "docs" / "clean-install-verification.md",
    REPO_ROOT / "docs" / "releases" / f"{PUBLIC_TAG}.md",
    REPO_ROOT / "docs" / "external-reviewer-walkthrough.md",
    REPO_ROOT / "docs" / "reviewer-checklist.md",
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
    REPO_ROOT / "docs" / "public-launch-readiness.md",
    REPO_ROOT / "docs" / "github-repo-settings.md",
    REPO_ROOT / "docs" / "public-repo-hygiene.md",
    REPO_ROOT / "docs" / "external-reviewer-walkthrough.md",
    REPO_ROOT / "docs" / "reviewer-checklist.md",
    REPO_ROOT / "docs" / "public-launch-messaging.md",
    REPO_ROOT / "docs" / "feedback-request-guide.md",
    REPO_ROOT / "docs" / "public-faq.md",
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


def _check_readme_safety() -> list[str]:
    errors: list[str] = []
    readme = REPO_ROOT / "README.md"
    text = _read(readme)
    lower = text.lower()

    if PUBLIC_TAG not in text:
        errors.append("README.md missing current status reference")

    # Reject stale RC current-status claims
    stale_rc_patterns = [
        r"Current Status \(v0\.5\.7-rc\d+\)",
        r"Current Status \(0\.5\.7rc\d+\)",
    ]
    for pattern in stale_rc_patterns:
        if re.search(pattern, text):
            errors.append(f"README.md contains stale RC current-status reference matching {pattern}")

    if "what this is" not in lower:
        errors.append("README.md missing 'What this is' section")

    if "what this is not" not in lower:
        errors.append("README.md missing 'What this is not' section")

    if "security.md" not in lower:
        errors.append("README.md missing link to SECURITY.md")

    if "contributing.md" not in lower:
        errors.append("README.md missing link to CONTRIBUTING.md")

    if "changelog" not in lower and "release notes" not in lower:
        errors.append("README.md missing link to changelog or release notes")

    forbidden_claims = [
        "live trading ready",
        "production trading ready",
        "safe to trade",
        "guaranteed profit",
        "profitable strategy",
        "verified alpha",
        "beats the market",
    ]
    for claim in forbidden_claims:
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
                errors.append(f"README.md contains forbidden claim: {claim}")

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
                errors.append(
                    f"[{rel}] Secret-like pattern: {m.group(0)[:40]}"
                )

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


def _check_version_match() -> list[str]:
    errors: list[str] = []
    pyproject = REPO_ROOT / "pyproject.toml"
    init = REPO_ROOT / "src" / "atlas_agent" / "__init__.py"

    import tomllib
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    toml_version = data.get("project", {}).get("version")
    if toml_version != PACKAGE_VERSION:
        errors.append(f"pyproject.toml version {toml_version} != {PACKAGE_VERSION}")

    init_text = init.read_text(encoding="utf-8")
    m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', init_text, re.MULTILINE)
    init_version = m.group(1) if m else None
    if init_version != PACKAGE_VERSION:
        errors.append(f"__init__.py version {init_version} != {PACKAGE_VERSION}")

    return errors


def _run_checks() -> dict:
    all_errors: list[str] = []
    all_errors.extend(_check_required_files())
    all_errors.extend(_check_readme_safety())
    all_errors.extend(_check_public_docs_safety())
    all_errors.extend(_check_no_staged_artifacts())
    all_errors.extend(_check_version_match())

    result = {
        "passed": len(all_errors) == 0,
        "package_version": PACKAGE_VERSION,
        "public_tag": PUBLIC_TAG,
        "errors": all_errors,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Public launch readiness check for Atlas Agent."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON (redacted).",
    )
    args = parser.parse_args()

    result = _run_checks()

    if args.json:
        # Redact errors before JSON output
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
        print("Public launch readiness check FAILED")
        for e in result["errors"]:
            print(f"  - {_redact(e)}")
        return 2

    print("Public launch readiness check PASSED")
    print(f"  Package version: {result['package_version']}")
    print(f"  Public tag: {result['public_tag']}")
    print(f"  Required files: {len(REQUIRED_FILES)} present")
    print(f"  Public docs safe: yes")
    print(f"  No staged artifacts: yes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
