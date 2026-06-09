#!/usr/bin/env python3
"""Validate the public trust center docs.

The check is deterministic and local. It does not load credentials, call
providers, contact brokers, publish artifacts, create tags, or modify runtime
state.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


CURRENT_RELEASE = "v0.6.7"
PACKAGE_VERSION = "0.6.7"
TRUST_README = Path("docs/trust/README.md")
TRUST_STATUS = Path("docs/trust/v0.6.7-status.md")

REQUIRED_README_SECTIONS = [
    "Current Public Release",
    "Security Posture",
    "Runtime Safety Defaults",
    "Provider Audit Evidence",
    "Release Assurance",
    "Auto-Updater Delivery",
    "Distribution Status",
    "What Is Ready",
    "What Is Not Ready",
    "Reviewer Entry Points",
    "Non-Claims",
]

REQUIRED_STATUS_SECTIONS = [
    "Release Identity",
    "Included Security Hardening",
    "Included Provider Evidence Tooling",
    "Assurance and CI Evidence",
    "Auto-Updater Status",
    "Safety Defaults",
    "Distribution Notes",
    "Known Limitations",
    "Verification Commands",
    "Reviewer Checklist",
]

REQUIRED_LINKS = {
    "docs/releases/v0.6.5.md": ("docs/releases/v0.6.5.md", "../releases/v0.6.5.md"),
    "docs/releases/v0.6.4.md": ("docs/releases/v0.6.4.md", "../releases/v0.6.4.md"),
    "docs/releases/v0.6.2.md": ("docs/releases/v0.6.2.md", "../releases/v0.6.2.md"),
    "docs/releases/v0.6.1.md": ("docs/releases/v0.6.1.md", "../releases/v0.6.1.md"),
    "docs/releases/v0.6.0.md": ("docs/releases/v0.6.0.md", "../releases/v0.6.0.md"),
    "SECURITY.md": ("SECURITY.md", "../../SECURITY.md"),
    "docs/security/release-readiness.md": (
        "docs/security/release-readiness.md",
        "../security/release-readiness.md",
    ),
    "docs/security/provider-audit-pack.md": (
        "docs/security/provider-audit-pack.md",
        "../security/provider-audit-pack.md",
    ),
    "docs/security/provider-evidence-index.md": (
        "docs/security/provider-evidence-index.md",
        "../security/provider-evidence-index.md",
    ),
    "docs/security/provider-preflight.md": (
        "docs/security/provider-preflight.md",
        "../security/provider-preflight.md",
    ),
    "docs/security/broker-safety.md": (
        "docs/security/broker-safety.md",
        "../security/broker-safety.md",
    ),
    "docs/security/dashboard-security.md": (
        "docs/security/dashboard-security.md",
        "../security/dashboard-security.md",
    ),
    "docs/security/approval-safety.md": (
        "docs/security/approval-safety.md",
        "../security/approval-safety.md",
    ),
    ".github/workflows/provider-audit-pack.yml": (
        ".github/workflows/provider-audit-pack.yml",
        "../../.github/workflows/provider-audit-pack.yml",
    ),
    ".github/workflows/release-assurance.yml": (
        ".github/workflows/release-assurance.yml",
        "../../.github/workflows/release-assurance.yml",
    ),
}

REQUIRED_FACTS = {
    "current public release v0.6.7": (("current public release", CURRENT_RELEASE),),
    "source package version 0.6.7": (
        ("source package version", PACKAGE_VERSION),
        ("package version in source metadata", PACKAGE_VERSION),
    ),
    "PyPI not published": (
        ("pypi publish: not performed",),
        ("pypi: not published",),
        ("pypi was not published",),
        ("no pypi publish has been performed",),
    ),
    "live trading disabled by default": (("live trading is disabled by default",),),
    "live submit disabled by default": (("live submit is disabled by default",),),
    "provider execution disabled by default": (
        ("provider execution is disabled by default",),
    ),
    "broker execution disabled by default": (
        ("broker execution is disabled by default",),
    ),
    "human approval required": (
        ("human approval is required",),
        ("human approval remains required",),
    ),
    "autonomous trading non-claim": (("autonomous trading is not claimed",),),
    "financial advice non-claim": (
        ("not financial advice",),
        ("financial advice is not claimed",),
    ),
    "release assurance": (("release assurance",),),
    "provider audit pack": (("provider audit pack",),),
    "updater delivery verification": (
        ("updater delivery verification",),
        ("auto-updater delivery", "verified"),
    ),
    "Telegram disabled by default or operator-gated": (
        ("telegram/remote control is disabled by default",),
        ("telegram/remote control", "operator-gated"),
        ("telegram/remote approval is not enabled by default",),
    ),
}

STALE_VERSION_PATTERNS = [
    re.compile(r"\bv0\.5\.7\.dev15\b"),
    re.compile(r"\bv0\.5\.7\.dev29\b"),
    re.compile(r"\b0\.5\.8\.dev0\b"),
    re.compile(r"\bv?0\.5\.9\.dev0\b"),
]

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


def _read_package_version(repo_root: Path) -> str:
    with (repo_root / "pyproject.toml").open("rb") as f:
        data = tomllib.load(f)
    version = data.get("project", {}).get("version")
    if not isinstance(version, str):
        raise ValueError("pyproject.toml is missing [project].version")
    return version


def _read_init_version(repo_root: Path) -> str:
    init_path = repo_root / "src" / "atlas_agent" / "__init__.py"
    text = _read_text(init_path)
    match = re.search(r"^__version__\s*=\s*[\"']([^\"']+)[\"']", text, re.M)
    if not match:
        raise ValueError("src/atlas_agent/__init__.py is missing __version__")
    return match.group(1)


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


def _markdown_link_targets(text: str) -> set[str]:
    return set(re.findall(r"\[[^\]]+\]\(([^)]+)\)", text))


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


def _validate_required_links(
    *,
    checks: list[Check],
    findings: list[str],
    repo_root: Path,
    readme_text: str,
) -> None:
    link_targets = _markdown_link_targets(readme_text)
    for canonical, variants in REQUIRED_LINKS.items():
        target_exists = (repo_root / canonical).exists()
        _add_check(
            checks,
            findings,
            f"link-target:{canonical}",
            target_exists,
            f"linked target exists: {canonical}",
            f"linked target is missing: {canonical}",
        )
        has_link = any(variant in link_targets for variant in variants)
        _add_check(
            checks,
            findings,
            f"trust-readme-link:{canonical}",
            has_link,
            f"{TRUST_README} links to {canonical}",
            f"{TRUST_README} does not link to {canonical}",
        )


def _validate_stale_versions(
    *,
    checks: list[Check],
    findings: list[str],
    docs: dict[Path, str],
) -> None:
    stale_findings: list[str] = []
    for rel_path, text in docs.items():
        for pattern in STALE_VERSION_PATTERNS:
            for match in pattern.finditer(text):
                stale_findings.append(
                    f"{rel_path}:{_line_no(text, match.start())}: stale current-status version '{match.group(0)}'"
                )
    _add_check(
        checks,
        findings,
        "stale-version-scan",
        not stale_findings,
        "trust docs do not mention stale current-status versions",
        "; ".join(stale_findings),
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
        "trust docs do not contain raw secret-like values",
        "; ".join(secret_findings),
    )


def validate_trust_center(repo_root: Path) -> ValidationResult:
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
    for rel_path in (TRUST_README, TRUST_STATUS):
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

    try:
        pyproject_version = _read_package_version(repo_root)
        init_version = _read_init_version(repo_root)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        return ValidationResult(
            repo_root=str(repo_root),
            checks=checks,
            findings=findings,
            errors=[f"could not read project version metadata: {exc}"],
        )

    _add_check(
        checks,
        findings,
        "pyproject-version",
        pyproject_version == PACKAGE_VERSION,
        f"pyproject.toml version is {PACKAGE_VERSION}",
        f"pyproject.toml version is {pyproject_version}, expected {PACKAGE_VERSION}",
    )
    _add_check(
        checks,
        findings,
        "init-version",
        init_version == PACKAGE_VERSION,
        f"src/atlas_agent/__init__.py version is {PACKAGE_VERSION}",
        f"src/atlas_agent/__init__.py version is {init_version}, expected {PACKAGE_VERSION}",
    )

    readme_text = docs.get(TRUST_README, "")
    status_text = docs.get(TRUST_STATUS, "")
    combined_text = "\n\n".join(docs.values())
    compact = _compact(combined_text)

    if readme_text:
        _validate_required_sections(
            checks=checks,
            findings=findings,
            rel_path=TRUST_README,
            text=readme_text,
            sections=REQUIRED_README_SECTIONS,
        )
        _validate_required_links(
            checks=checks,
            findings=findings,
            repo_root=repo_root,
            readme_text=readme_text,
        )

    if status_text:
        _validate_required_sections(
            checks=checks,
            findings=findings,
            rel_path=TRUST_STATUS,
            text=status_text,
            sections=REQUIRED_STATUS_SECTIONS,
        )

    for fact, variants in REQUIRED_FACTS.items():
        _add_check(
            checks,
            findings,
            f"fact:{fact}",
            _contains_any_fact(compact, variants),
            f"trust docs state {fact}",
            f"trust docs do not state {fact}",
        )

    _add_check(
        checks,
        findings,
        f"mentions:{CURRENT_RELEASE}",
        CURRENT_RELEASE in combined_text,
        f"trust docs mention {CURRENT_RELEASE}",
        f"trust docs do not mention {CURRENT_RELEASE}",
    )
    _add_check(
        checks,
        findings,
        "no-dev-current-release",
        "v0.5.9.dev0" not in combined_text and "0.5.9.dev0" not in combined_text,
        "trust docs do not claim v0.5.9.dev0 as current public release",
        "trust docs mention v0.5.9.dev0/0.5.9.dev0 as a stale public status",
    )
    _add_check(
        checks,
        findings,
        "no-v062-as-current-release",
        "Current Status (v0.6.2)" not in combined_text,
        "trust docs do not claim v0.6.2 as the current prepared release",
        "trust docs still claim v0.6.2 as the current prepared release",
    )
    _add_check(
        checks,
        findings,
        "no-v063-as-current-release",
        "Current Status (v0.6.3)" not in combined_text,
        "trust docs do not claim v0.6.3 as the current prepared release",
        "trust docs still claim v0.6.3 as the current prepared release",
    )

    _validate_stale_versions(checks=checks, findings=findings, docs=docs)
    _validate_secret_patterns(checks=checks, findings=findings, docs=docs)

    return ValidationResult(
        repo_root=str(repo_root),
        checks=checks,
        findings=findings,
        errors=errors,
    )


def _print_text_result(result: ValidationResult) -> None:
    if result.status == "passed":
        print("Trust center check PASSED")
    elif result.status == "failed":
        print("Trust center check FAILED")
    else:
        print("Trust center check ERROR")

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
    parser = argparse.ArgumentParser(description="Validate Atlas Agent trust center docs.")
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

    result = validate_trust_center(args.repo_root)
    if args.json:
        print(json.dumps(result.to_jsonable(), indent=2, sort_keys=True))
    else:
        _print_text_result(result)
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
