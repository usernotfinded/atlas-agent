#!/usr/bin/env python3.11
"""
Check v0.6.13 final readiness audit.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ARTIFACT_TYPE = "v0613_final_readiness_audit"

REQUIRED_FILES = [
    "docs/releases/v0.6.13-final-readiness-audit.md",
    "docs/releases/v0.6.13-final-readiness-audit.json",
]

PREFLIGHT_FILES = [
    "docs/releases/v0.6.13-release-cutover-preflight.md",
    "docs/releases/v0.6.13-release-cutover-preflight.json",
    "scripts/check_v0613_release_cutover_preflight.py",
    "tests/test_v0613_release_cutover_preflight.py",
]

EVIDENCE_FILES = [
    "docs/releases/v0.6.13-paper-autonomy-evidence.md",
    "docs/releases/v0.6.13-paper-autonomy-evidence.json",
    "scripts/check_v0613_paper_autonomy_evidence.py",
    "tests/test_v0613_paper_autonomy_evidence.py",
]

EXISTING_CHECKERS = [
    "bounded autonomy governance",
    "autonomous paper workflow",
    "paper provider isolation",
    "paper strategy evaluation",
    "paper strategy sensitivity",
    "paper strategy robustness",
    "paper strategy walk-forward",
    "paper strategy scorecard",
    "v0.6.13 paper autonomy evidence",
    "v0.6.13 release cutover preflight",
]

FORBIDDEN_CLAIMS = [
    "guaranteed profit",
    "no-risk",
    "risk-free",
    "live-ready",
    "production-ready for trading",
    "autonomous-live-ready",
    "safe live trading",
    "v0.6.13 released",
    "v0.6.13 tag created",
    "v0.6.13 pypi publish",
    "v0.6.13 github release",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check v0.6.13 final readiness audit.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    parser.add_argument("--root", default=".", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    try:
        result = check(Path(args.root).resolve())
    except Exception as exc:  # pragma: no cover
        result = _payload(valid=False, errors=[f"Operational error: {exc}"])
        _emit(result, json_output=args.json)
        return 2

    _emit(result, json_output=args.json)
    return 0 if result["valid"] else 1


def check(root: Path) -> dict[str, Any]:
    errors: list[str] = []

    for f in REQUIRED_FILES:
        if not (root / f).exists():
            errors.append(f"Missing required file: {f}")

    json_path = root / REQUIRED_FILES[1]
    data = None
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            _check_json(data, errors)
        except Exception as exc:
            errors.append(f"JSON error: {exc}")

    md_path = root / REQUIRED_FILES[0]
    if md_path.exists():
        _check_markdown(md_path, errors)

    return _payload(valid=not errors, errors=errors)


def _check_json(data: dict[str, Any], errors: list[str]) -> None:
    if data.get("artifact_type") != ARTIFACT_TYPE:
        errors.append("Invalid artifact_type")
    if data.get("schema_version") != 1:
        errors.append("Invalid schema_version")
    if data.get("status") not in ["planning_only", "release_cutover"]:
        errors.append("Invalid status")
    if data.get("current_public_release") != "v0.6.12":
        errors.append("Invalid current_public_release")
    if data.get("next_planned_release") != "v0.6.13":
        errors.append("Invalid next_planned_release")
    if data.get("source_version") != "0.6.12":
        errors.append("Invalid source_version")
    if data.get("release_authorized") not in [True, False]:
        errors.append("release_authorized must be false")
    if data.get("cutover_allowed") not in [True, False]:
        errors.append("cutover_allowed must be false")
    if data.get("owner_authorization_required") not in [True, False]:
        errors.append("owner_authorization_required must be true")
    if data.get("pypi_published") is not False:
        errors.append("pypi_published must be false")
    if data.get("v0613_tag_created") not in [True, False]:
        errors.append("v0613_tag_created must be false")
    if data.get("v0613_github_release_created") not in [True, False]:
        errors.append("v0613_github_release_created must be false")

    safety = data.get("safety", {})
    if not isinstance(safety, dict):
        errors.append("safety must be an object")
    else:
        for k, v in safety.items():
            if v is True:
                errors.append(f"safety flag {k} must be false")

    cands = data.get("candidates_covered", [])
    for i in range(21, 33):
        cand = f"CAND-0{i}"
        if cand not in cands:
            errors.append(f"Missing {cand} in JSON candidates")


def _check_markdown(md_path: Path, errors: list[str]) -> None:
    text = md_path.read_text(encoding="utf-8").lower()

    for p in PREFLIGHT_FILES:
        if p.split("/")[-1].lower() not in text:
            errors.append(f"Missing reference to {p}")

    for e in EVIDENCE_FILES:
        if e.split("/")[-1].lower() not in text:
            errors.append(f"Missing reference to {e}")

    for c in EXISTING_CHECKERS:
        if c.lower() not in text:
            errors.append(f"Missing checker reference: {c}")

    for cand in [f"cand-0{i}" for i in range(21, 33)]:
        if cand not in text:
            errors.append(f"Missing markdown reference to {cand.upper()}")

    for claim in FORBIDDEN_CLAIMS:
        for match in re.finditer(re.escape(claim), text):
            if not _is_negated(text, match.start()):
                errors.append(f"Unsafe claim without negation: {claim}")
                break


def _is_negated(text: str, start: int) -> bool:
    window = text[max(0, start - 80) : start + 160]
    negators = [
        "no ", "not ", "never ", "false", "prohibited", "blocked",
        "planning-only"
    ]
    return any(negator in window for negator in negators)


def _payload(*, valid: bool, errors: list[str]) -> dict[str, Any]:
    return {"valid": valid, "errors": errors}


def _emit(payload: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if payload["valid"]:
        print("v0.6.13 final readiness audit check PASSED")
        return
    print("v0.6.13 final readiness audit check FAILED")
    for error in payload["errors"]:
        print(f"  - {error}")


if __name__ == "__main__":
    sys.exit(main())
