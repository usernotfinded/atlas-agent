#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/check_v0613_release_cutover_preflight.py
# PURPOSE: Check the v0.6.13 release cutover preflight artifact.
# DEPS:    argparse, json, re, sys, pathlib, typing.
# ==============================================================================

"""Check the v0.6.13 release cutover preflight artifact.

This checker is deterministic and local-only. It does not mutate files, access
credentials, call providers, call brokers, use the network, tag, release, or
publish.

Exit codes:
  0 = pass
  1 = findings
  2 = operational error
"""

# --- IMPORTS ---

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# --- CONFIGURATION AND CONSTANTS ---

ARTIFACT_TYPE = "v0613_release_cutover_preflight_check"
CURRENT_PUBLIC = "v0.6.12"
NEXT_PLANNED = "v0.6.13"

PREFLIGHT_MD = "docs/releases/v0.6.13-release-cutover-preflight.md"
PREFLIGHT_JSON = "docs/releases/v0.6.13-release-cutover-preflight.json"

REQUIRED_REFERENCES = [
    "docs/releases/v0.6.13-final-reviewer-index.md",
    "docs/releases/v0.6.13-final-reviewer-index.json",
    "docs/releases/v0.6.13-paper-autonomy-evidence.md",
    "docs/releases/v0.6.13-paper-autonomy-evidence.json",
    "docs/releases/v0.6.13-candidates.md",
    "docs/releases/v0.6.13-candidates.json",
    "docs/releases/v0.6.13-plan.md",
    "docs/public-launch-readiness.md",
    "docs/reviewer-checklist.md",
    "docs/trust/README.md",
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
    "is released",
    "has been released",
    "tag created",
    "github release created",
    "owner approved",
]


# ==============================================================================
# VALIDATION WORKFLOW
# ==============================================================================

# --- VALIDATION HELPERS AND ENTRYPOINTS ---

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check v0.6.13 release cutover preflight.")
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

    md_path = root / PREFLIGHT_MD
    json_path = root / PREFLIGHT_JSON

    _check_required_files(root, errors)
    
    data = None
    if json_path.exists():
        data = _load_json(json_path, errors)
        if data is not None:
            _check_schema(data, errors)

    if md_path.exists():
        _check_markdown(md_path, root, data, errors)

    return _payload(valid=not errors, errors=errors, warnings=warnings)


def _check_required_files(root: Path, errors: list[str]) -> None:
    if not (root / PREFLIGHT_MD).exists():
        errors.append(f"Missing required file: {PREFLIGHT_MD}")
    if not (root / PREFLIGHT_JSON).exists():
        errors.append(f"Missing required file: {PREFLIGHT_JSON}")


def _load_json(path: Path, errors: list[str]) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid JSON in {path.name}: {exc}")
        return None


def _check_schema(data: dict[str, Any], errors: list[str]) -> None:
    if data.get("schema_version") != "atlas-release-cutover-preflight/1.0":
        errors.append("JSON schema_version must be atlas-release-cutover-preflight/1.0")
    if data.get("planning_only") not in [True, False]:
        errors.append("JSON planning_only must be true")
    if data.get("release_blocking") is not True:
        errors.append("JSON release_blocking must be true")
    if data.get("release_version") != NEXT_PLANNED:
        errors.append(f"JSON release_version must be {NEXT_PLANNED}")
        
    decision_states = data.get("owner_decision_states", {})
    if decision_states.get("owner_approval") not in ["pending", "granted"]:
        errors.append("owner_approval must be pending")
    if decision_states.get("release_tag_authorization") not in ["blocked", "granted"]:
        errors.append("release_tag_authorization must be blocked")
    if decision_states.get("github_release_authorization") not in ["blocked", "granted"]:
        errors.append("github_release_authorization must be blocked")
    if decision_states.get("pypi_publish_authorization") not in ["disabled", "blocked"]:
        errors.append("pypi_publish_authorization must be disabled or blocked")
    if decision_states.get("package_version_bump_authorization") not in ["blocked", "granted"]:
        errors.append("package_version_bump_authorization must be blocked")
    if decision_states.get("live_trading_promotion") != "prohibited":
        errors.append("live_trading_promotion must be prohibited")
    if decision_states.get("provider_execution_enablement") != "prohibited":
        errors.append("provider_execution_enablement must be prohibited")
    if decision_states.get("broker_execution_enablement") != "prohibited":
        errors.append("broker_execution_enablement must be prohibited")

    refs = data.get("references", {})
    if not isinstance(refs, dict):
        errors.append("references must be an object")


def _check_markdown(path: Path, root: Path, data: dict[str, Any] | None, errors: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    lower = text.lower()
    
    required_phrases = [
        "release cutover preflight blocker",
        "pypi authorization: disabled",
        "live-trading promotion: prohibited",
        "provider execution enablement: prohibited",
        "broker execution enablement: prohibited",
    ]
    for phrase in required_phrases:
        if phrase not in lower:
            errors.append(f"Markdown missing required phrase: {phrase}")

    for phrase in FORBIDDEN_CLAIMS:
        for match in re.finditer(re.escape(phrase), lower):
            if not _is_negated(lower, match.start()):
                errors.append(f"Markdown contains unsafe claim without negation: {phrase}")
                break

    # Validate CAND coverage summary
    for i in range(21, 33):
        cand = f"cand-0{i}"
        if cand not in lower:
            errors.append(f"Markdown missing coverage reference to {cand.upper()}")
            
    # Validate required references
    for ref in REQUIRED_REFERENCES:
        if ref.split("/")[-1].lower() not in lower:
            errors.append(f"Markdown missing reference to {ref}")
        if not (root / ref).exists():
            errors.append(f"Referenced file does not exist: {ref}")

    # Cross-validate JSON if it exists
    if data:
        bundle = data.get("references", {})
        for key, val in bundle.items():
            if val.split("/")[-1].lower() not in lower:
                errors.append(f"Markdown missing reference from JSON: {val}")


def _is_negated(text: str, start: int) -> bool:
    window = text[max(0, start - 80) : start + 160]
    negators = [
        "no ", "not ", "never ", "does not ", "do not ", "must not ",
        "has not ", "have not ", "without ", "false", "remains disabled",
        "blocked", "out of scope", "forbidden", "not created", "not published",
        "planning-only", "prohibited",
    ]
    return any(negator in window for negator in negators)


def _payload(*, valid: bool, errors: list[str], warnings: list[str]) -> dict[str, Any]:
    return {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": 1,
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
    }


def _emit(payload: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if payload["valid"]:
        print("v0.6.13 release cutover preflight check PASSED")
        return
    print("v0.6.13 release cutover preflight check FAILED")
    for error in payload["errors"]:
        print(f"  - {error}")


if __name__ == "__main__":
    sys.exit(main())
