#!/usr/bin/env python3
"""Static/local check that reviewer-facing onboarding materials exist and are safe.

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

CURRENT_PACKAGE_VERSION = "0.5.9.4"
HISTORICAL_STABLE_TAG = "v0.5.8.1"

ONBOARDING_DOC_PATHS = [
    REPO_ROOT / "docs" / "external-reviewer-walkthrough.md",
    REPO_ROOT / "docs" / "reviewer-checklist.md",
]

LINKING_DOC_PATHS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "public-launch-readiness.md",
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


def _check_onboarding_docs_exist() -> list[str]:
    errors: list[str] = []
    for path in ONBOARDING_DOC_PATHS:
        if not path.exists():
            rel = path.relative_to(REPO_ROOT)
            errors.append(f"Onboarding doc missing: {rel}")
    return errors


def _check_linking_docs() -> list[str]:
    errors: list[str] = []
    for path in LINKING_DOC_PATHS:
        if not path.exists():
            continue
        text = _read(path)
        lower = text.lower()
        rel = str(path.relative_to(REPO_ROOT))
        if "external-reviewer-walkthrough.md" not in text and "reviewer walkthrough" not in lower:
            errors.append(f"[{rel}] Missing link to reviewer walkthrough")
        if "reviewer-checklist.md" not in text and "reviewer checklist" not in lower:
            errors.append(f"[{rel}] Missing link to reviewer checklist")
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


def _check_onboarding_doc_safety() -> list[str]:
    errors: list[str] = []
    required_phrases = [
        "live trading disabled by default",
        "provider execution remains locked",
        "trust remains blocked",
        "no credentials required",
        "not financial advice",
    ]

    for path in ONBOARDING_DOC_PATHS:
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

        for phrase in required_phrases:
            if phrase.lower() not in lower:
                errors.append(f"[{rel}] Required safety phrase missing: {phrase}")

    return errors


def _check_safe_commands_present() -> list[str]:
    errors: list[str] = []
    walkthrough = REPO_ROOT / "docs" / "external-reviewer-walkthrough.md"
    if walkthrough.exists():
        text = walkthrough.read_text(encoding="utf-8").lower()
        required_commands = [
            "check_version_consistency.py",
            "check_forbidden_claims.py",
            "check_public_docs_consistency.py",
            "check_public_launch_readiness.py",
            "check_reviewer_onboarding.py",
            "release_check.sh --quick",
        ]
        for cmd in required_commands:
            if cmd.lower() not in text:
                errors.append(f"[external-reviewer-walkthrough.md] Missing safe command: {cmd}")
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


def _run_checks() -> dict:
    all_errors: list[str] = []
    all_errors.extend(_check_onboarding_docs_exist())
    all_errors.extend(_check_linking_docs())
    all_errors.extend(_check_version_match())
    all_errors.extend(_check_onboarding_doc_safety())
    all_errors.extend(_check_safe_commands_present())
    all_errors.extend(_check_no_staged_artifacts())

    result = {
        "passed": len(all_errors) == 0,
        "package_version": CURRENT_PACKAGE_VERSION,
        "public_tag": HISTORICAL_STABLE_TAG,
        "errors": all_errors,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reviewer onboarding check for Atlas Agent."
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
        print("Reviewer onboarding check FAILED")
        for e in result["errors"]:
            print(f"  - {_redact(e)}")
        return 2

    print("Reviewer onboarding check PASSED")
    print(f"  Current package version: {result['package_version']}")
    print(f"  Historical stable tag: {result['public_tag']}")
    print(f"  Onboarding docs present: {len(ONBOARDING_DOC_PATHS)}")
    print(f"  Docs safe: yes")
    print(f"  No staged artifacts: yes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
