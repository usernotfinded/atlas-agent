#!/usr/bin/env python3
"""Validate a product demo evidence bundle.

Static, local-only, and read-only. Does not load credentials, make network calls,
submit broker orders, call providers, or enable live trading.

Exit codes:
  0 = bundle valid
  1 = blocking findings
  2 = operational error (e.g., missing bundle directory)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_FILES = [
    "evidence.json",
    "summary.md",
    "safety-boundaries.md",
    "artifacts-index.md",
    "commands.txt",
    "checksums.sha256",
]

REQUIRED_JSON_KEYS = [
    "schema_version",
    "generated_at",
    "atlas_version",
    "demo_mode",
    "live_trading_enabled",
    "provider_execution",
    "broker_execution",
    "credentials_loaded",
    "network_required",
    "demo_commands_run",
    "output_files",
    "artifact_paths",
    "safety_checks_summary",
]

REQUIRED_SAFETY_SUMMARY_KEYS = [
    "live_trading_disabled",
    "paper_mode",
    "provider_execution_locked",
    "broker_execution_blocked",
    "no_credentials_required",
    "no_network_calls",
]

REQUIRED_SUMMARY_PHRASES = [
    "not financial advice",
    "paper-only",
    "no credentials",
    "no live trading",
    "provider execution",
    "broker order",
]

REQUIRED_SAFETY_BOUNDARY_PHRASES = [
    "paper-only",
    "offline",
    "credential-free",
    "no live trading",
    "provider execution",
    "broker order",
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

FORBIDDEN_SCRIPT_PHRASES = [
    "rm -rf /",
    "set_secret",
    "enable_live_trading = true",
    "enable_live_submit = true",
    "can_submit=true",
    "--mode live",
    "curl ",
    "wget ",
    "provider.execute",
    "execute_provider",
    "broker.submit",
    "submit_order",
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


def _check_required_files(bundle_dir: Path) -> list[str]:
    violations: list[str] = []
    for name in REQUIRED_FILES:
        if not (bundle_dir / name).exists():
            violations.append(f"Required file missing: {name}")
    return violations


def _load_json(bundle_dir: Path) -> dict[str, Any]:
    path = bundle_dir / "evidence.json"
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"evidence.json is not valid JSON: {e}")


def _check_json_schema(evidence: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for key in REQUIRED_JSON_KEYS:
        if key not in evidence:
            violations.append(f"evidence.json missing key: {key}")

    if evidence.get("demo_mode") != "paper/dry-run":
        violations.append(
            f"evidence.json demo_mode must be 'paper/dry-run', got {evidence.get('demo_mode')!r}"
        )

    unsafe_booleans = {
        "live_trading_enabled": False,
        "provider_execution": False,
        "broker_execution": False,
        "credentials_loaded": False,
        "network_required": False,
    }
    for key, expected in unsafe_booleans.items():
        if key in evidence and evidence[key] is not expected:
            violations.append(f"evidence.json unsafe value: {key}={evidence[key]!r} (expected {expected!r})")

    summary = evidence.get("safety_checks_summary", {})
    for key in REQUIRED_SAFETY_SUMMARY_KEYS:
        if key not in summary:
            violations.append(f"evidence.json safety_checks_summary missing key: {key}")
        elif summary[key] is not True:
            violations.append(f"evidence.json safety_checks_summary['{key}'] must be True, got {summary.get(key)!r}")

    if not isinstance(evidence.get("demo_commands_run"), list):
        violations.append("evidence.json demo_commands_run must be a list")

    if not isinstance(evidence.get("output_files"), dict):
        violations.append("evidence.json output_files must be an object")

    if not isinstance(evidence.get("artifact_paths"), dict):
        violations.append("evidence.json artifact_paths must be an object")

    return violations


def _check_referenced_files_exist(bundle_dir: Path, evidence: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for key, rel in evidence.get("output_files", {}).items():
        if not (bundle_dir / rel).exists():
            violations.append(f"output_files['{key}'] references missing file: {rel}")
    for key, rel in evidence.get("artifact_paths", {}).items():
        if not (bundle_dir / rel).exists():
            violations.append(f"artifact_paths['{key}'] references missing file: {rel}")
    return violations


def _check_required_phrases(bundle_dir: Path) -> list[str]:
    violations: list[str] = []
    summary_path = bundle_dir / "summary.md"
    safety_path = bundle_dir / "safety-boundaries.md"
    for phrase in REQUIRED_SUMMARY_PHRASES:
        if not summary_path.exists() or phrase.lower() not in _read(summary_path).lower():
            violations.append(f"[summary.md] Missing required safety phrase: {phrase}")
    for phrase in REQUIRED_SAFETY_BOUNDARY_PHRASES:
        if not safety_path.exists() or phrase.lower() not in _read(safety_path).lower():
            violations.append(f"[safety-boundaries.md] Missing required safety phrase: {phrase}")
    return violations


def _check_forbidden_claims(bundle_dir: Path) -> list[str]:
    violations: list[str] = []
    for name in ["summary.md", "safety-boundaries.md", "artifacts-index.md", "commands.txt"]:
        path = bundle_dir / name
        if not path.exists():
            continue
        text = _read(path).lower()
        rel = path.relative_to(bundle_dir)
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


def _check_forbidden_script_patterns(bundle_dir: Path) -> list[str]:
    violations: list[str] = []
    path = bundle_dir / "commands.txt"
    if not path.exists():
        return violations
    text = _read(path).lower()
    for phrase in FORBIDDEN_SCRIPT_PHRASES:
        if phrase.lower() in text:
            violations.append(f"[commands.txt] Forbidden command pattern: {phrase}")
    return violations


def _check_secrets(bundle_dir: Path) -> list[str]:
    violations: list[str] = []
    for path in sorted(bundle_dir.rglob("*")):
        if not path.is_file() or path.name == "checksums.sha256":
            continue
        try:
            text = _read(path)
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(bundle_dir)
        for pattern in SECRET_PATTERNS:
            for m in pattern.finditer(text):
                violations.append(
                    f"[{rel}] Secret-like pattern matched: {m.group(0)[:40]}"
                )
    return violations


def _check_checksums(bundle_dir: Path) -> list[str]:
    violations: list[str] = []
    checksums_path = bundle_dir / "checksums.sha256"
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
        file_path = bundle_dir / rel_path
        if not file_path.exists():
            violations.append(f"[checksums.sha256] Referenced file missing: {rel_path}")
            continue
        actual = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if actual != digest:
            violations.append(
                f"[checksums.sha256] Checksum mismatch for {rel_path}"
            )
    return violations


def run_checks(bundle_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not bundle_dir.exists():
        return {
            "passed": False,
            "errors": [f"Evidence bundle directory does not exist: {bundle_dir}"],
            "warnings": [],
        }

    errors.extend(_check_required_files(bundle_dir))

    evidence: dict[str, Any] = {}
    try:
        evidence = _load_json(bundle_dir)
    except ValueError as e:
        errors.append(str(e))

    if evidence:
        errors.extend(_check_json_schema(evidence))
        errors.extend(_check_referenced_files_exist(bundle_dir, evidence))

    errors.extend(_check_required_phrases(bundle_dir))
    errors.extend(_check_forbidden_claims(bundle_dir))
    errors.extend(_check_forbidden_script_patterns(bundle_dir))
    errors.extend(_check_secrets(bundle_dir))
    errors.extend(_check_checksums(bundle_dir))

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a product demo evidence bundle. Static and local-only."
    )
    parser.add_argument(
        "bundle_dir",
        nargs="?",
        default=os.environ.get("ATLAS_PRODUCT_DEMO_EVIDENCE_DIR"),
        help="Directory containing the evidence bundle. Defaults to ATLAS_PRODUCT_DEMO_EVIDENCE_DIR.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    if not args.bundle_dir:
        parser.error("bundle_dir is required (or set ATLAS_PRODUCT_DEMO_EVIDENCE_DIR)")

    bundle_dir = Path(args.bundle_dir).resolve()
    result = run_checks(bundle_dir)

    if args.json:
        summary = (
            "Product demo evidence check PASSED"
            if result["passed"]
            else "Product demo evidence check FAILED"
        )
        print(
            json.dumps(
                {
                    "passed": result["passed"],
                    "bundle_dir": str(bundle_dir),
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
        print("Product demo evidence check FAILED")
        for error in result["errors"]:
            print(f"  - {error}")
    else:
        print("Product demo evidence check PASSED")
        print(f"  Bundle: {bundle_dir}")

    if result["warnings"]:
        for warning in result["warnings"]:
            print(f"  WARN: {warning}")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
