#!/usr/bin/env python3.11
"""Check the v0.6.15 final human review release-readiness audit.

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

ARTIFACT_TYPE = "v0615_final_readiness_audit"
CURRENT_PUBLIC = "v0.6.14"
NEXT_PLANNED = "v0.6.15"
SOURCE_VERSION = "0.6.14"
POST_RELEASE_CURRENT = "v0.6.15"
POST_RELEASE_NEXT = "v0.6.16"
POST_RELEASE_SOURCE = "0.6.15"

AUDIT_MD = "docs/releases/v0.6.15-final-readiness-audit.md"
AUDIT_JSON = "docs/releases/v0.6.15-final-readiness-audit.json"
RELEASE_METADATA = "docs/releases/release-metadata.json"

EXPECTED_CANDIDATES = [
    "CAND-001",
    "CAND-002",
    "CAND-003",
    "CAND-004",
    "CAND-005",
    "CAND-006",
]

CHAIN_CANDIDATES = EXPECTED_CANDIDATES[:-1]

REQUIRED_CHECK_FRAGMENTS = [
    "scripts/check_paper_human_review_pack.py",
    "scripts/check_paper_human_review_ledger.py",
    "scripts/check_paper_human_review_policy.py",
    "scripts/check_paper_human_review_replay.py",
    "scripts/check_v0615_paper_human_review_evidence.py",
    "scripts/check_v0615_final_readiness_audit.py",
    "scripts/check_version_consistency.py",
    "scripts/check_release_metadata.py",
    "scripts/check_forbidden_claims.py",
    "scripts/check_public_docs_consistency.py",
    "scripts/check_trust_center.py",
    "atlas backtest portfolio-review-pack",
    "atlas backtest portfolio-review-ledger",
    "atlas backtest portfolio-review-policy",
    "atlas backtest portfolio-review-replay",
]

REQUIRED_SAFETY_FLAGS = [
    "no_live_trading",
    "no_live_submit",
    "no_broker_calls",
    "no_provider_calls",
    "no_notifications_sent",
    "no_orders_generated",
    "no_real_human_approval",
    "no_credentials_or_secrets",
    "no_profit_claim",
    "no_absolute_safety_claim",
    "no_no_risk_claim",
    "no_live_readiness_claim",
    "no_autonomous_live_readiness_claim",
]

GATE_FILES = [
    "scripts/dev_check.sh",
    "scripts/ci_check.sh",
    "scripts/release_check.sh",
    ".github/workflows/ci.yml",
]

GATE_REQUIRED_FRAGMENTS = [
    "scripts/check_v0615_paper_human_review_evidence.py",
    "scripts/check_v0615_final_readiness_audit.py",
    "tests/test_v0615_final_readiness_audit.py",
]

CHAIN_GATE_FRAGMENTS = [
    "scripts/check_paper_human_review_pack.py",
    "scripts/check_paper_human_review_ledger.py",
    "scripts/check_paper_human_review_policy.py",
    "scripts/check_paper_human_review_replay.py",
    "scripts/check_v0615_paper_human_review_evidence.py",
]

FORBIDDEN_CLAIMS = [
    "guaranteed profit",
    "profit guarantee",
    "guaranteed returns",
    "risk-free",
    "zero risk",
    "no risk",
    "no-risk",
    "live ready",
    "live-ready",
    "ready for live",
    "live trading ready",
    "safe live trading",
    "production-ready for trading",
    "production trading readiness",
    "autonomous-live-ready",
    "autonomous live ready",
    "autonomous live trading ready",
    "approved for live",
    "outperforms the market",
    "will outperform",
    "real-money ready",
]

FORBIDDEN_RELEASE_CLAIMS = [
    "v0.6.15 is released",
    "v0.6.15 has been released",
    "v0.6.15 released",
    "current public release: v0.6.15",
    '"current_public_release": "v0.6.15"',
    "tag v0.6.15 created",
    "v0.6.15 tag created",
    "github release v0.6.15 published",
    "v0.6.15 github release created",
    "v0.6.15 pypi publish",
    "pypi was published",
    "published to pypi",
    '"pypi_published": true',
]

FORBIDDEN_AUTHORIZATION_CLAIMS = [
    "owner authorization granted",
    "owner authorized release",
    "release authorized",
    "cutover authorized",
    "approved release cutover",
    "release cutover approved",
    "owner has authorized",
]

FORBIDDEN_SIDE_EFFECTS = [
    "live trading enabled",
    "live submit enabled",
    "broker calls made",
    "provider calls made",
    "notifications sent",
    "orders generated",
    "orders submitted",
    "orders were submitted",
    "order submission",
    "broker order submission",
    "submitted to market",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check v0.6.15 final readiness audit."
    )
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

    md_path = root / AUDIT_MD
    json_path = root / AUDIT_JSON

    _check_required_files(md_path, json_path, errors)
    data = _load_json(json_path, errors)
    if data is not None:
        _check_schema(data, errors)
        _check_candidates(data, errors)
        _check_required_checks(data, errors)
        _check_reference_paths(root, data, errors)

    _check_markdown(md_path, errors)
    _check_repository_posture(root, errors)
    _check_gate_integration(root, errors)

    return _payload(valid=not errors, errors=errors, warnings=warnings)


def _check_required_files(md_path: Path, json_path: Path, errors: list[str]) -> None:
    if not md_path.exists():
        errors.append(f"Missing required file: {AUDIT_MD}")
    if not json_path.exists():
        errors.append(f"Missing required file: {AUDIT_JSON}")


def _load_json(path: Path, errors: list[str]) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid audit JSON: {exc}")
        return None
    if not isinstance(data, dict):
        errors.append("Audit JSON must be an object")
        return None
    return data


def _check_schema(data: dict[str, Any], errors: list[str]) -> None:
    expected = {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": 1,
        "release": NEXT_PLANNED,
        "release_state": "planning_only",
        "current_public_release": CURRENT_PUBLIC,
        "next_planned_release": NEXT_PLANNED,
        "source_version": SOURCE_VERSION,
        "pypi_published": False,
        "tag_created": False,
        "github_release_created": False,
        "mode": "paper",
        "paper_only": True,
        "non_executable": True,
        "provider_required": False,
        "broker_required": False,
        "network_required": False,
        "live_submit_enabled": False,
        "orders_generated": False,
        "notifications_sent": False,
        "real_human_approval": False,
        "not_financial_advice": True,
        "not_live_ready": True,
        "owner_authorization_required": True,
        "release_authorized": False,
        "cutover_allowed": False,
    }
    for key, value in expected.items():
        if data.get(key) != value:
            errors.append(f"Audit JSON {key} must be {value!r}, got {data.get(key)!r}")

    if data.get("decision") not in {
        "go_for_owner_authorized_cutover",
        "no_go_needs_more_work",
    }:
        errors.append("Audit JSON decision must be a supported Go/No-Go value")

    safety = data.get("safety")
    if not isinstance(safety, dict):
        errors.append("Audit JSON safety must be an object")
        return
    for key in REQUIRED_SAFETY_FLAGS:
        if safety.get(key) is not True:
            errors.append(f"Audit JSON safety.{key} must be true")


def _check_candidates(data: dict[str, Any], errors: list[str]) -> None:
    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        errors.append("Audit JSON candidates must be a list")
        return

    ids = [item.get("id") for item in candidates if isinstance(item, dict)]
    if ids != EXPECTED_CANDIDATES:
        errors.append(f"Audit JSON candidates must exactly list {EXPECTED_CANDIDATES}")
        return

    by_id = {item["id"]: item for item in candidates if isinstance(item, dict) and "id" in item}
    for cand in CHAIN_CANDIDATES:
        item = by_id[cand]
        if item.get("status") != "complete":
            errors.append(f"Audit JSON {cand} status must be 'complete'")
        if item.get("mode") != "paper":
            errors.append(f"Audit JSON {cand} mode must be 'paper'")
        if item.get("paper_only") is not True:
            errors.append(f"Audit JSON {cand} paper_only must be true")
        if item.get("gate_integrated") is not True:
            errors.append(f"Audit JSON {cand} gate_integrated must be true")

    final = by_id["CAND-006"]
    final_title = str(final.get("title", "")).lower()
    if "final human review release-readiness audit" not in final_title:
        errors.append("Audit JSON CAND-006 must be represented as the final readiness audit")
    if final.get("status") != "complete":
        errors.append("Audit JSON CAND-006 status must be 'complete'")
    if final.get("mode") != "paper":
        errors.append("Audit JSON CAND-006 mode must be 'paper'")


def _check_required_checks(data: dict[str, Any], errors: list[str]) -> None:
    checks = data.get("required_checks")
    if not isinstance(checks, list):
        errors.append("Audit JSON required_checks must be a list")
        return

    joined = "\n".join(str(item) for item in checks)
    for fragment in REQUIRED_CHECK_FRAGMENTS:
        if fragment not in joined:
            errors.append(f"Audit JSON required_checks missing {fragment}")


def _check_reference_paths(root: Path, data: dict[str, Any], errors: list[str]) -> None:
    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        return

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        for key in ["docs", "checkers", "tests", "demos"]:
            refs = candidate.get(key, [])
            if refs is None:
                refs = []
            if not isinstance(refs, list):
                errors.append(f"Audit JSON {candidate.get('id', '<unknown>')}.{key} must be a list")
                continue
            for ref in refs:
                if not isinstance(ref, str):
                    errors.append(f"Audit JSON {candidate.get('id', '<unknown>')}.{key} contains non-string")
                    continue
                if ref == "not_applicable":
                    continue
                if not (root / ref).exists():
                    errors.append(f"Audit JSON references missing file: {ref}")


def _check_markdown(path: Path, errors: list[str]) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    lower = text.lower()
    required = [
        "planning-only",
        "not a release cutover",
        "current public release remains v0.6.14",
        "source/package version remains 0.6.14",
        "pypi remains unpublished",
        "no tag/release is created",
        "no owner authorization is implied",
        "paper-only",
        "no provider calls",
        "no broker calls",
        "no live submit",
        "no real notifications",
        "no orders generated/submitted",
        "no live-readiness claims",
        "no profit claims",
        "no absolute-safety claims",
        "no claims that risk is eliminated",
        "no future-performance claims",
        "not financial advice",
        "decision: go_for_owner_authorized_cutover",
    ]
    for item in required:
        if item not in lower:
            errors.append(f"Audit Markdown missing required wording: {item}")

    for cand in EXPECTED_CANDIDATES:
        if cand.lower() not in lower:
            errors.append(f"Audit Markdown missing candidate reference: {cand}")

    _scan_phrases(AUDIT_MD, text, FORBIDDEN_CLAIMS, "unsafe claim", errors)
    _scan_phrases(AUDIT_MD, text, FORBIDDEN_RELEASE_CLAIMS, "v0.6.15 release claim", errors)
    _scan_phrases(AUDIT_MD, text, FORBIDDEN_AUTHORIZATION_CLAIMS, "release authorization claim", errors)
    _scan_phrases(AUDIT_MD, text, FORBIDDEN_SIDE_EFFECTS, "side-effect claim", errors)


def _check_repository_posture(root: Path, errors: list[str]) -> None:
    """Accept the audited pre-cutover state or the authorized post-cutover state."""
    metadata_path = root / RELEASE_METADATA
    metadata = _load_json(metadata_path, errors)
    if metadata is None:
        return

    posture = (
        metadata.get("source_version"),
        metadata.get("current_public_release"),
        metadata.get("next_planned_release"),
    )
    allowed = {
        (SOURCE_VERSION, CURRENT_PUBLIC, NEXT_PLANNED),
        (POST_RELEASE_SOURCE, POST_RELEASE_CURRENT, POST_RELEASE_NEXT),
    }
    if posture not in allowed:
        errors.append(f"release metadata posture is not an audited v0.6.15 state: {posture!r}")
    if metadata.get("pypi_published") is not False:
        errors.append("release metadata pypi_published must be false")

    pyproject = _read(root / "pyproject.toml")
    init_text = _read(root / "src" / "atlas_agent" / "__init__.py")
    expected_source = str(metadata.get("source_version", ""))
    if f'version = "{expected_source}"' not in pyproject:
        errors.append("pyproject.toml version must match release metadata")
    if f'__version__ = "{expected_source}"' not in init_text:
        errors.append("src/atlas_agent/__init__.py version must match release metadata")


def _check_gate_integration(root: Path, errors: list[str]) -> None:
    for rel in GATE_FILES:
        path = root / rel
        if not path.exists():
            errors.append(f"Missing gate file: {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        for fragment in GATE_REQUIRED_FRAGMENTS:
            if fragment not in text:
                if rel == "scripts/release_check.sh" and "./scripts/dev_check.sh" in text:
                    continue
                errors.append(f"{rel} missing gate integration fragment: {fragment}")

    for rel in GATE_FILES:
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for fragment in CHAIN_GATE_FRAGMENTS:
            if fragment not in text:
                if rel == "scripts/release_check.sh" and "./scripts/dev_check.sh" in text:
                    continue
                errors.append(f"{rel} missing chain gate integration fragment: {fragment}")


def _scan_phrases(
    rel: str,
    text: str,
    phrases: list[str],
    label: str,
    errors: list[str],
) -> None:
    lower = text.lower()
    for phrase in phrases:
        for match in re.finditer(re.escape(phrase), lower):
            if not _is_allowed_context(lower, match.start()):
                errors.append(f"{rel} contains {label} without allowed context: {phrase}")
                break


def _is_allowed_context(text: str, start: int) -> bool:
    window = text[max(0, start - 100) : start + 180]
    allowed = [
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
        "disabled by default",
        "blocked",
        "out of scope",
        "forbidden",
        "not created",
        "not published",
        "planning only",
        "planning-only",
        "future separately authorized",
        "separately authorized",
        "separate owner authorization",
        "owner authorization is not implied",
        "requires owner authorization",
        "required before",
    ]
    return any(marker in window for marker in allowed)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _payload(*, valid: bool, errors: list[str], warnings: list[str]) -> dict[str, Any]:
    return {
        "artifact_type": "v0615_final_readiness_audit_check",
        "schema_version": 1,
        "valid": valid,
        "release": NEXT_PLANNED,
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
        print("v0.6.15 final readiness audit check PASSED")
        return
    print("v0.6.15 final readiness audit check FAILED")
    for error in payload["errors"]:
        print(f"  - {error}")


if __name__ == "__main__":
    sys.exit(main())
