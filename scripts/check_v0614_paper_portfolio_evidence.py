#!/usr/bin/env python3.11
"""Check the v0.6.14 paper portfolio evidence bundle.

This checker is deterministic and local-only. It does not mutate files, access
credentials, call providers, call brokers, use the network, tag, release, or
publish.

Exit codes:
  0 = pass
  1 = findings
  2 = operational error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ARTIFACT_TYPE = "v0614_paper_portfolio_evidence"
CURRENT_PUBLIC = "v0.6.13"
NEXT_PLANNED = "v0.6.14"
SOURCE_VERSION = "0.6.13"

EVIDENCE_MD = "docs/releases/v0.6.14-paper-portfolio-evidence.md"
EVIDENCE_JSON = "docs/releases/v0.6.14-paper-portfolio-evidence.json"

EXPECTED_CANDIDATES = [
    "CAND-001",
    "CAND-002",
    "CAND-003",
    "CAND-004",
    "CAND-005",
    "CAND-006",
]

FORBIDDEN_CLAIMS = [
    "guaranteed profit",
    "profit guarantee",
    "no-risk",
    "zero risk",
    "risk-free",
    "live ready",
    "live-ready",
    "ready for live",
    "safe live trading",
    "production-ready for trading",
    "production trading readiness",
    "autonomous-live-ready",
    "autonomous live ready",
    "approved for live",
    "outperforms the market",
    "will outperform",
]

FORBIDDEN_RELEASE_CLAIMS = [
    "v0.6.14 is released",
    "v0.6.14 has been released",
    "v0.6.14 released",
    "current public release: v0.6.14",
    '"current_public_release": "v0.6.14"',
    "tag v0.6.14 created",
    "v0.6.14 tag created",
    "github release v0.6.14 published",
    "v0.6.14 github release created",
    "v0.6.14 pypi publish",
    '"pypi_published": true',
]

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check v0.6.14 paper portfolio evidence bundle.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output.")
    parser.add_argument("--root", default=".", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    try:
        result = check(Path(args.root).resolve())
    except Exception as exc:  # pragma: no cover
        result = _payload(valid=False, errors=[f"Operational error: {exc}"], warnings=[])
        _emit(result, json_output=args.json)
        return 2

    _emit(result, json_output=args.json)
    return 0 if result["valid"] else 1


def check(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    md_path = root / EVIDENCE_MD
    json_path = root / EVIDENCE_JSON

    _check_required_files(root, md_path, json_path, errors)
    data = _load_evidence_json(json_path, errors)
    if data is not None:
        _check_schema(data, errors)
        _check_candidates(data, errors)
        _check_evidence_references(root, data, errors)
    _check_markdown(md_path, errors)
    _check_release_metadata(root, errors)

    return _payload(valid=not errors, errors=errors, warnings=warnings)


def _check_required_files(root: Path, md_path: Path, json_path: Path, errors: list[str]) -> None:
    if not md_path.exists():
        errors.append(f"Missing required file: {EVIDENCE_MD}")
    if not json_path.exists():
        errors.append(f"Missing required file: {EVIDENCE_JSON}")


def _load_evidence_json(path: Path, errors: list[str]) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid evidence JSON: {exc}")
        return None


def _check_schema(data: dict[str, Any], errors: list[str]) -> None:
    expected = {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": 1,
        "release": "v0.6.14",
        "release_state": "planning_only",
        "current_public_release": CURRENT_PUBLIC,
        "source_version": SOURCE_VERSION,
        "pypi_published": False,
        "mode": "paper",
        "provider_required": False,
        "broker_required": False,
        "network_required": False,
        "live_readiness": False,
        "not_financial_advice": True,
    }
    for key, value in expected.items():
        if data.get(key) != value:
            errors.append(f"Evidence JSON {key} must be {value!r}")

    safety = data.get("safety")
    if not isinstance(safety, dict):
        errors.append("Evidence JSON safety must be an object")
        return
    for key in [
        "no_live_trading",
        "no_broker_calls",
        "no_provider_calls",
        "no_notifications_sent",
        "no_orders_generated",
        "no_profit_claim",
        "no_live_readiness_claim",
        "no_autonomous_live_readiness_claim",
    ]:
        if safety.get(key) is not True:
            errors.append(f"Evidence JSON safety.{key} must be true")


def _check_candidates(data: dict[str, Any], errors: list[str]) -> None:
    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        errors.append("Evidence JSON candidates must be a list")
        return

    ids = [item.get("id") for item in candidates if isinstance(item, dict)]
    if ids != EXPECTED_CANDIDATES:
        errors.append(f"Evidence JSON candidates must exactly list {EXPECTED_CANDIDATES}")


def _check_evidence_references(root: Path, data: dict[str, Any], errors: list[str]) -> None:
    for key in ["required_commands", "required_docs", "required_demos", "required_checkers", "required_tests"]:
        values = data.get(key)
        if not isinstance(values, list):
            errors.append(f"Evidence JSON {key} must be a list")
            continue
        if key == "required_commands":
            continue
            
        for rel in values:
            if not isinstance(rel, str):
                errors.append(f"Evidence JSON {key} contains non-string")
                continue
            path = root / rel
            if not path.exists():
                errors.append(f"Evidence JSON {key} references missing file: {rel}")
            
            if key == "required_demos":
                if path.exists():
                    content = path.read_text(encoding="utf-8")
                    if "--mode live" in content:
                        errors.append(f"Demo {rel} references live mode")
                    if "atlas submit" in content or "atlas execute" in content:
                        errors.append(f"Demo {rel} references order submission")


def _check_markdown(path: Path, errors: list[str]) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    lower = text.lower()
    required = [
        "planning-only",
        "not financial advice",
        "current public release: v0.6.13",
        "source version: 0.6.13",
        "no tag/release is created",
        "no pypi publication has occurred",
        "paper-only",
        "no provider calls",
        "no broker calls",
    ]
    for item in required:
        if item not in lower:
            errors.append(f"Evidence Markdown missing required wording: {item}")
    _scan_forbidden_claims(EVIDENCE_MD, text, errors)
    _scan_release_claims(EVIDENCE_MD, text, errors)


def _check_release_metadata(root: Path, errors: list[str]) -> None:
    pyproject = _read(root / "pyproject.toml")
    init_py = _read(root / "src" / "atlas_agent" / "__init__.py")
    if SOURCE_VERSION not in pyproject:
        errors.append(f"Source/package version must remain {SOURCE_VERSION} in pyproject.toml")
    if SOURCE_VERSION not in init_py:
        errors.append(f"Source/package version must remain {SOURCE_VERSION} in src/atlas_agent/__init__.py")

def _scan_forbidden_claims(rel: str, text: str, errors: list[str]) -> None:
    lower = text.lower()
    for phrase in FORBIDDEN_CLAIMS:
        for match in re.finditer(re.escape(phrase), lower):
            if not _is_negated(lower, match.start()):
                errors.append(f"{rel} contains unsafe claim without negation: {phrase}")
                break


def _scan_release_claims(rel: str, text: str, errors: list[str]) -> None:
    lower = text.lower()
    for phrase in FORBIDDEN_RELEASE_CLAIMS:
        for match in re.finditer(re.escape(phrase), lower):
            if not _is_negated(lower, match.start()):
                errors.append(f"{rel} contains v0.6.14 release claim without negation: {phrase}")
                break


def _is_negated(text: str, start: int) -> bool:
    window = text[max(0, start - 80) : start + 160]
    negators = [
        "no ",
        "not ",
        "never ",
        "does not ",
        "do not ",
        "must not ",
        "has not ",
        "have not ",
        "without ",
        "false",
        "remains disabled",
        "blocked",
        "out of scope",
        "forbidden",
        "not created",
        "not published",
        "planning only",
        "planning-only",
    ]
    return any(negator in window for negator in negators)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _payload(*, valid: bool, errors: list[str], warnings: list[str]) -> dict[str, Any]:
    return {
        "artifact_type": "v0614_paper_portfolio_evidence_check",
        "schema_version": 1,
        "valid": valid,
        "release": "v0.6.14",
        "current_public_release": CURRENT_PUBLIC,
        "source_version": SOURCE_VERSION,
        "errors": errors,
        "warnings": warnings,
    }


def _emit(payload: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if payload["valid"]:
        print("v0.6.14 paper portfolio evidence check PASSED")
        return
    print("v0.6.14 paper portfolio evidence check FAILED")
    for error in payload["errors"]:
        print(f"  - {error}")


if __name__ == "__main__":
    sys.exit(main())
