#!/usr/bin/env python3
"""Validate a reviewer trust snapshot.

Static, local-only, and read-only. Does not load credentials, make network calls,
submit broker orders, call providers, or enable live trading.

Exit codes:
  0 = snapshot valid
  1 = blocking findings
  2 = operational error (e.g., missing snapshot directory)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
BUILDER_SCRIPT = REPO_ROOT / "scripts" / "build_reviewer_trust_snapshot.py"

REQUIRED_FILES = [
    "reviewer-trust-snapshot.json",
    "reviewer-trust-snapshot.md",
]

OPTIONAL_FILES = [
    "checksums.sha256",
]

REQUIRED_JSON_KEYS = [
    "schema_version",
    "generated_at",
    "repository",
    "source_version",
    "current_public_release",
    "next_planned_release",
    "pypi_published",
    "release_status",
    "ci_runs",
    "evidence_bundle",
    "safety_invariants",
    "capability_status",
    "forbidden_claims_absent",
    "generated_files",
    "checksums",
]

REQUIRED_SAFETY_INVARIANTS = {
    "live_trading_disabled_by_default": True,
    "live_submit_disabled_by_default": True,
    "provider_execution_disabled_by_default": True,
    "broker_execution_disabled_by_default": True,
    "credentials_required_for_demo": False,
    "network_required_for_demo": False,
    "autonomous_trading_claimed": False,
    "profit_claims_absent": True,
    "no_risk_claims_absent": True,
}

REQUIRED_MARKDOWN_SECTIONS = [
    "## Release identity",
    "## Release status",
    "## CI evidence",
    "## Demo evidence reference",
    "## Safety posture",
    "## What is disabled",
    "## What this snapshot does not prove",
    "## Reviewer verification commands",
    "## Disclaimer",
]

REQUIRED_MARKDOWN_PHRASES = [
    "not financial advice",
    "paper-first",
    "sandbox-only",
    "safe-by-default",
    "live trading is disabled by default",
    "provider execution",
    "broker execution",
    "pypi was not published",
    "does not prove profitability",
    "does not prove production readiness",
]

FORBIDDEN_MARKETPLACE_PHRASES = [
    "live trading ready",
    "production trading ready",
    "production-ready trading",
    "real-money ready",
    "real money ready",
    "autonomous trading ready",
    "fully autonomous",
    "safe live trading",
    "safe to trade real money",
    "guaranteed profit",
    "guaranteed returns",
    "profitable strategy",
    "verified alpha",
    "beats the market",
    "beat the market",
    "makes money",
    "earns money",
    "passive income",
    "financial freedom",
    "zero risk",
    "risk-free",
    "risk free",
    "no risk",
    "use atlas with real money",
    "connect real broker credentials",
    "trade real money",
    "start live trading now",
    "enable live trading",
    "link your broker account",
    "provider execution enabled",
    "unlock provider execution",
    "unlock the provider",
    "broker order submission enabled",
    "enable broker submission",
    "can_submit=true",
    "auto_within_limits",
    "set and forget",
    "unattended live trading",
]

SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\bsk-proj-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\bAPCA-[A-Z0-9]{10,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{10,}", re.IGNORECASE),
]

NEGATIVE_CONTEXT_INDICATORS = (
    "not ",
    "does not",
    "never",
    "no ",
    "avoid",
    "disclaimer",
    "prohibited",
    "forbidden",
    "must not",
    "cannot",
    "do not",
    "is not",
    "are not",
    "without",
    "fail closed",
    "not yet",
    "not implemented",
    "not enabled",
    "not authorized",
    "not a ",
    "not ready",
    "remains disabled",
    "remains locked",
    "remains blocked",
    "out of scope",
    "does not prove",
    "disabled by default",
)


def _read(path: Path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _sentence_around(text: str, start: int, end: int) -> str:
    boundary_chars = {".", "!", "?", "\n"}
    s = start
    while s > 0 and text[s - 1] not in boundary_chars:
        s -= 1
    e = end
    while e < len(text) and text[e] not in boundary_chars:
        e += 1
    return text[s:e]


def _check_required_files(snapshot_dir: Path) -> list[str]:
    violations: list[str] = []
    for name in REQUIRED_FILES:
        if not (snapshot_dir / name).exists():
            violations.append(f"Required file missing: {name}")
    return violations


def _load_json(snapshot_dir: Path) -> dict[str, Any]:
    path = snapshot_dir / "reviewer-trust-snapshot.json"
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"reviewer-trust-snapshot.json is not valid JSON: {e}")


def _check_json_schema(snapshot: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for key in REQUIRED_JSON_KEYS:
        if key not in snapshot:
            violations.append(f"reviewer-trust-snapshot.json missing key: {key}")

    if snapshot.get("schema_version") != "atlas-reviewer-trust-snapshot/1.0":
        violations.append(
            f"schema_version must be 'atlas-reviewer-trust-snapshot/1.0', "
            f"got {snapshot.get('schema_version')!r}"
        )

    if snapshot.get("repository") != "usernotfinded/atlas-agent":
        violations.append(
            f"repository must be 'usernotfinded/atlas-agent', got {snapshot.get('repository')!r}"
        )

    if snapshot.get("pypi_published") is not False:
        violations.append(
            f"pypi_published must be False, got {snapshot.get('pypi_published')!r}"
        )

    invariants = snapshot.get("safety_invariants", {})
    if not isinstance(invariants, dict):
        violations.append("safety_invariants must be an object")
    else:
        for key, expected in REQUIRED_SAFETY_INVARIANTS.items():
            if key not in invariants:
                violations.append(f"safety_invariants missing key: {key}")
            elif invariants[key] is not expected:
                violations.append(
                    f"safety_invariants['{key}'] must be {expected!r}, got {invariants[key]!r}"
                )

    forbidden = snapshot.get("forbidden_claims_absent", {})
    if not isinstance(forbidden, dict):
        violations.append("forbidden_claims_absent must be an object")
    else:
        for key, expected in forbidden.items():
            if expected is not True:
                violations.append(
                    f"forbidden_claims_absent['{key}'] must be True, got {expected!r}"
                )

    generated_files = snapshot.get("generated_files", {})
    for name in ["reviewer-trust-snapshot.json", "reviewer-trust-snapshot.md", "checksums.sha256"]:
        if generated_files.get(name) != name:
            violations.append(f"generated_files['{name}'] must be '{name}'")

    return violations


def _check_markdown_sections(snapshot_dir: Path) -> list[str]:
    violations: list[str] = []
    md_path = snapshot_dir / "reviewer-trust-snapshot.md"
    if not md_path.exists():
        return violations

    text = _read(md_path).lower()
    for section in REQUIRED_MARKDOWN_SECTIONS:
        if section.lower() not in text:
            violations.append(f"[reviewer-trust-snapshot.md] Missing required section: {section}")

    for phrase in REQUIRED_MARKDOWN_PHRASES:
        if phrase.lower() not in text:
            violations.append(f"[reviewer-trust-snapshot.md] Missing required phrase: {phrase}")

    return violations


def _check_forbidden_claims(snapshot_dir: Path) -> list[str]:
    violations: list[str] = []
    for name in ["reviewer-trust-snapshot.md"]:
        path = snapshot_dir / name
        if not path.exists():
            continue
        text = _read(path).lower()
        rel = path.relative_to(snapshot_dir)
        for phrase in FORBIDDEN_MARKETPLACE_PHRASES:
            start = text.find(phrase)
            while start != -1:
                end = start + len(phrase)
                sentence = _sentence_around(text, start, end).lower()
                if not any(ind in sentence for ind in NEGATIVE_CONTEXT_INDICATORS):
                    violations.append(
                        f"[{rel}] Forbidden phrase '{phrase}' outside negative context"
                    )
                start = text.find(phrase, end)
    return violations


def _check_secrets(snapshot_dir: Path) -> list[str]:
    violations: list[str] = []
    for path in sorted(snapshot_dir.rglob("*")):
        if not path.is_file() or path.name == "checksums.sha256":
            continue
        try:
            text = _read(path)
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(snapshot_dir)
        for pattern in SECRET_PATTERNS:
            for m in pattern.finditer(text):
                violations.append(
                    f"[{rel}] Secret-like pattern matched: {m.group(0)[:40]}"
                )
    return violations


def _check_checksums(snapshot_dir: Path) -> list[str]:
    violations: list[str] = []
    checksums_path = snapshot_dir / "checksums.sha256"
    if not checksums_path.exists():
        return violations

    entries: list[tuple[str, str]] = []
    for lineno, line in enumerate(_read(checksums_path).splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            violations.append(f"[checksums.sha256] Malformed line {lineno}: {line!r}")
            continue
        digest, rel_path = parts
        entries.append((digest, rel_path))

    seen: set[str] = set()
    for digest, rel_path in entries:
        if rel_path in seen:
            violations.append(f"[checksums.sha256] Duplicate entry: {rel_path}")
            continue
        seen.add(rel_path)
        file_path = snapshot_dir / rel_path
        if not file_path.exists():
            violations.append(f"[checksums.sha256] Referenced file missing: {rel_path}")
            continue
        actual = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if actual != digest:
            violations.append(
                f"[checksums.sha256] Checksum mismatch for {rel_path}"
            )
    return violations


def _run_self_test() -> dict[str, Any]:
    """Build a deterministic snapshot in a temp dir and validate it."""
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp) / "snapshot"
        result = subprocess.run(
            [sys.executable, str(BUILDER_SCRIPT), "--output-dir", str(output_dir), "--deterministic"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return {
                "passed": False,
                "errors": [f"Self-test builder failed: {result.stderr}"],
                "warnings": [],
            }
        return run_checks(output_dir)


def run_checks(snapshot_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not snapshot_dir.exists():
        return {
            "passed": False,
            "errors": [f"Snapshot directory does not exist: {snapshot_dir}"],
            "warnings": [],
        }

    errors.extend(_check_required_files(snapshot_dir))

    snapshot: dict[str, Any] = {}
    try:
        snapshot = _load_json(snapshot_dir)
    except ValueError as e:
        errors.append(str(e))

    if snapshot:
        errors.extend(_check_json_schema(snapshot))

    errors.extend(_check_markdown_sections(snapshot_dir))
    errors.extend(_check_forbidden_claims(snapshot_dir))
    errors.extend(_check_secrets(snapshot_dir))
    errors.extend(_check_checksums(snapshot_dir))

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a reviewer trust snapshot. Static and local-only."
    )
    parser.add_argument(
        "snapshot_dir",
        nargs="?",
        default=os.environ.get("ATLAS_REVIEWER_TRUST_SNAPSHOT_DIR"),
        help="Directory containing the snapshot. Defaults to ATLAS_REVIEWER_TRUST_SNAPSHOT_DIR.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Build a deterministic snapshot in a temp dir and validate it.",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        result = _run_self_test()
        snapshot_dir = "<self-test temp dir>"
    elif not args.snapshot_dir:
        parser.error("snapshot_dir is required (or set ATLAS_REVIEWER_TRUST_SNAPSHOT_DIR)")
    else:
        snapshot_dir = Path(args.snapshot_dir).resolve()
        result = run_checks(snapshot_dir)

    if args.json:
        summary = (
            "Reviewer trust snapshot check PASSED"
            if result["passed"]
            else "Reviewer trust snapshot check FAILED"
        )
        print(
            json.dumps(
                {
                    "passed": result["passed"],
                    "snapshot_dir": str(snapshot_dir),
                    "summary": summary,
                    "errors": result["errors"],
                    "warnings": result["warnings"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if result["passed"] else 1

    if result["errors"]:
        print("Reviewer trust snapshot check FAILED")
        for error in result["errors"]:
            print(f"  - {error}")
    else:
        print("Reviewer trust snapshot check PASSED")
        print(f"  Snapshot: {snapshot_dir}")

    if result["warnings"]:
        for warning in result["warnings"]:
            print(f"  WARN: {warning}")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
