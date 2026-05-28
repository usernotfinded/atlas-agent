#!/usr/bin/env python3
"""Static check for launch/feedback messaging safety.

Deterministic and local. Does not:
- call network
- post to social platforms
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

PACKAGE_VERSION = "0.5.8.dev0"
PUBLIC_TAG = "v0.5.7"

LAUNCH_DOC_PATHS = [
    REPO_ROOT / "docs" / "public-launch-messaging.md",
    REPO_ROOT / "docs" / "feedback-request-guide.md",
    REPO_ROOT / "docs" / "public-faq.md",
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
    "profit guarantee",
    "profitable strategy",
    "verified alpha",
    "beats the market",
    "beat the market",
    "makes money",
    "earns money",
    "passive income",
    "financial freedom",
]

# Hype words that should not appear in launch messaging.
_HYPE_WORDS = [
    "revolutionary",
    "game-changing",
    "guaranteed",
    "unstoppable",
    "fully autonomous",
    "production-grade trading bot",
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


def _check_launch_docs_exist() -> list[str]:
    errors: list[str] = []
    for path in LAUNCH_DOC_PATHS:
        if not path.exists():
            rel = path.relative_to(REPO_ROOT)
            errors.append(f"Launch doc missing: {rel}")
    return errors


def _check_linking_docs() -> list[str]:
    errors: list[str] = []
    for path in LINKING_DOC_PATHS:
        if not path.exists():
            continue
        text = _read(path)
        lower = text.lower()
        rel = str(path.relative_to(REPO_ROOT))
        if "public-launch-messaging.md" not in text and "launch messaging" not in lower:
            errors.append(f"[{rel}] Missing link to public launch messaging")
        if "feedback-request-guide.md" not in text and "feedback request guide" not in lower:
            errors.append(f"[{rel}] Missing link to feedback request guide")
        if "public-faq.md" not in text and "public faq" not in lower:
            errors.append(f"[{rel}] Missing link to public FAQ")
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


def _check_launch_doc_safety() -> list[str]:
    errors: list[str] = []
    required_phrases = [
        "live trading disabled by default",
        "provider execution remains locked",
        "trust remains blocked",
        "not financial advice",
    ]

    for path in LAUNCH_DOC_PATHS:
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

        for hype in _HYPE_WORDS:
            if hype in lower:
                errors.append(f"[{rel}] Hype word: {hype}")

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


def _check_no_real_money_invite() -> list[str]:
    errors: list[str] = []
    for path in LAUNCH_DOC_PATHS:
        if not path.exists():
            continue
        text = _read(path).lower()
        rel = str(path.relative_to(REPO_ROOT))
        inviting_phrases = [
            "use atlas with real money",
            "connect real broker credentials",
            "trade real money",
            "start live trading now",
            "enable live trading",
        ]
        for phrase in inviting_phrases:
            if phrase not in text:
                continue
            idx = text.index(phrase)
            context_start = max(0, idx - 120)
            context_end = min(len(text), idx + 120)
            context = text[context_start:context_end]
            negative_indicators = (
                "not ", "do not", "never", "no ", "avoid",
                "must not", "cannot", "prohibited", "forbidden",
                "do not ask", "do not create", "do not request",
            )
            if not any(ind in context for ind in negative_indicators):
                errors.append(f"[{rel}] May invite real-money trading: {phrase}")
    return errors


def _check_no_credentials_request() -> list[str]:
    errors: list[str] = []
    for path in LAUNCH_DOC_PATHS:
        if not path.exists():
            continue
        text = _read(path).lower()
        rel = str(path.relative_to(REPO_ROOT))
        if "send me your api key" in text or "share your credentials" in text:
            errors.append(f"[{rel}] Requests credentials")
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
    all_errors.extend(_check_launch_docs_exist())
    all_errors.extend(_check_linking_docs())
    all_errors.extend(_check_version_match())
    all_errors.extend(_check_launch_doc_safety())
    all_errors.extend(_check_no_real_money_invite())
    all_errors.extend(_check_no_credentials_request())
    all_errors.extend(_check_no_staged_artifacts())

    result = {
        "passed": len(all_errors) == 0,
        "package_version": PACKAGE_VERSION,
        "public_tag": PUBLIC_TAG,
        "errors": all_errors,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Public launch messaging check for Atlas Agent."
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
        print("Public launch messaging check FAILED")
        for e in result["errors"]:
            print(f"  - {_redact(e)}")
        return 2

    print("Public launch messaging check PASSED")
    print(f"  Package version: {result['package_version']}")
    print(f"  Public tag: {result['public_tag']}")
    print(f"  Launch docs present: {len(LAUNCH_DOC_PATHS)}")
    print(f"  Docs safe: yes")
    print(f"  No staged artifacts: yes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
