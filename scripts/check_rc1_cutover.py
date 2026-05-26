#!/usr/bin/env python3
"""Verify the repo is internally consistent for v0.5.7-rc1.

Deterministic and local. Does not:
- tag
- push
- publish
- build packages
- call network
- load credentials
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_VERSION = "0.5.7rc2"
PUBLIC_TAG = "v0.5.7-rc2"

# Forbidden positive claims about live trading / provider execution / broker execution / trust.
FORBIDDEN_POSITIVE_CLAIMS = [
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

# Fragments that should not appear in public docs.
FORBIDDEN_FRAGMENTS = [
    "/Users/",
    "/private/var/",
]

# Secret-like patterns.
SECRET_PATTERNS = [
    r"\bsk-[A-Za-z0-9]{10,}",
    r"\bAPCA-[A-Z0-9]{10,}",
    r"\bBearer\s+[A-Za-z0-9._~+/=-]{10,}",
    r"\bAuthorization:\s*Bearer\s+[A-Za-z0-9._~+/=-]+",
]

# Absolute path patterns.
ABSOLUTE_PATH_PATTERNS = [
    r"/Users/[A-Za-z0-9_/-]+",
    r"/private/var/[A-Za-z0-9_/-]+",
]


def _read(path: Path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _check_version_consistency() -> list[str]:
    errors: list[str] = []
    pyproject_path = REPO_ROOT / "pyproject.toml"
    init_path = REPO_ROOT / "src" / "atlas_agent" / "__init__.py"
    readme_path = REPO_ROOT / "README.md"
    changelog_path = REPO_ROOT / "CHANGELOG.md"
    release_note_path = REPO_ROOT / "docs" / "releases" / f"{PUBLIC_TAG}.md"
    checklist_path = REPO_ROOT / "docs" / "release-checklist.md"

    if pyproject_path.exists():
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        toml_version = data.get("project", {}).get("version")
        if toml_version != PACKAGE_VERSION:
            errors.append(
                f"pyproject.toml version {toml_version!r} != {PACKAGE_VERSION!r}"
            )
    else:
        errors.append("pyproject.toml not found")

    if init_path.exists():
        init_text = init_path.read_text(encoding="utf-8")
        m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', init_text, re.MULTILINE)
        init_version = m.group(1) if m else None
        if init_version != PACKAGE_VERSION:
            errors.append(
                f"__init__.py version {init_version!r} != {PACKAGE_VERSION!r}"
            )
    else:
        errors.append("__init__.py not found")

    if readme_path.exists():
        readme_text = readme_path.read_text(encoding="utf-8")
        if PUBLIC_TAG not in readme_text:
            errors.append("README.md missing current status reference to RC1")
        stale = [
            r"Current Status \(v0\.5\.7\.dev5[0-9]\)",
            r"Current Status \(0\.5\.7\.dev5[0-9]\)",
        ]
        for pattern in stale:
            if re.search(pattern, readme_text):
                errors.append(f"README.md contains stale dev current-status reference")
    else:
        errors.append("README.md not found")

    if changelog_path.exists():
        changelog_text = changelog_path.read_text(encoding="utf-8")
        if f"[{PACKAGE_VERSION}]" not in changelog_text:
            errors.append("CHANGELOG.md missing RC1 entry")
    else:
        errors.append("CHANGELOG.md not found")

    if not release_note_path.exists():
        errors.append(f"Release note missing: {release_note_path}")

    if checklist_path.exists():
        checklist_text = checklist_path.read_text(encoding="utf-8")
        if PUBLIC_TAG not in checklist_text:
            errors.append("release-checklist.md missing RC1 reference")
    else:
        errors.append("release-checklist.md not found")

    return errors


def _scan_text(text: str, rel_path: str) -> list[str]:
    errors: list[str] = []
    lower = text.lower()

    for phrase in FORBIDDEN_POSITIVE_CLAIMS:
        for m in re.finditer(re.escape(phrase), lower):
            sentence_start = max(0, m.start() - 120)
            sentence_end = min(len(lower), m.end() + 120)
            sentence = lower[sentence_start:sentence_end]
            negative_indicators = (
                "not ", "does not", "never", "no ", "avoid",
                "disclaimer", "prohibited", "forbidden", "must not",
                "cannot", "do not", "is not", "are not", "without",
                "fail closed", "not yet", "not implemented", "not enabled",
                "not authorized", "not a ", "not ready", "remains disabled",
                "remains locked", "remains blocked",
            )
            if not any(ind in sentence for ind in negative_indicators):
                errors.append(
                    f"[{rel_path}] Forbidden positive claim '{phrase}'"
                )

    for frag in FORBIDDEN_FRAGMENTS:
        if frag in text:
            errors.append(f"[{rel_path}] Forbidden fragment '{frag}'")

    for pattern in SECRET_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            errors.append(
                f"[{rel_path}] Secret-like pattern matched: {m.group(0)[:40]}"
            )

    for pattern in ABSOLUTE_PATH_PATTERNS:
        for m in re.finditer(pattern, text):
            errors.append(
                f"[{rel_path}] Absolute path matched: {m.group(0)[:60]}"
            )

    return errors


def _check_no_package_artifacts_staged() -> list[str]:
    errors: list[str] = []
    git_index = REPO_ROOT / ".git" / "index"
    # Use git diff --cached to detect staged files
    import subprocess
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    staged = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    forbidden_prefixes = ("dist/", "build/", "*.egg-info")
    for f in staged:
        if f.startswith(forbidden_prefixes) or f.endswith(".egg-info/"):
            errors.append(f"Package artifact staged: {f}")
    return errors


def main() -> int:
    all_errors: list[str] = []

    all_errors.extend(_check_version_consistency())

    public_docs = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "CHANGELOG.md",
        REPO_ROOT / "docs" / "releases" / f"{PUBLIC_TAG}.md",
        REPO_ROOT / "docs" / "release-checklist.md",
        REPO_ROOT / "docs" / "provider-safety-dossier.md",
        REPO_ROOT / "docs" / "examples" / "provider-safety-dossier-workflow.md",
        REPO_ROOT / "docs" / "release-candidate-readiness.md",
        REPO_ROOT / "docs" / "release-candidate-cutover.md",
    ]

    for path in public_docs:
        if not path.exists():
            continue
        rel = path.relative_to(REPO_ROOT)
        text = _read(path)
        all_errors.extend(_scan_text(text, str(rel)))

    all_errors.extend(_check_no_package_artifacts_staged())

    if all_errors:
        print("RC2 cutover check FAILED")
        for e in all_errors:
            print(f"  - {e}")
        return 2

    print(f"RC2 cutover check PASSED: package={PACKAGE_VERSION} public_tag={PUBLIC_TAG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
