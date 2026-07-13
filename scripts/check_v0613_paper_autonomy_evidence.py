#!/usr/bin/env python3
"""Check the v0.6.13 paper-autonomy evidence bundle.

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


ARTIFACT_TYPE = "v0613_paper_autonomy_evidence"
CURRENT_PUBLIC = "v0.6.12"
NEXT_PLANNED = "v0.6.13"
SOURCE_VERSION = "0.6.13"

EVIDENCE_MD = "docs/releases/v0.6.13-paper-autonomy-evidence.md"
EVIDENCE_JSON = "docs/releases/v0.6.13-paper-autonomy-evidence.json"

EXPECTED_CANDIDATES = [
    "CAND-021",
    "CAND-022",
    "CAND-023",
    "CAND-024",
    "CAND-025",
    "CAND-026",
    "CAND-027",
    "CAND-028",
    "CAND-029",
]

REQUIRED_REFERENCES = [
    "scripts/check_bounded_autonomy_governance.py",
    "scripts/check_autonomous_paper_workflow_demo.py",
    "scripts/check_paper_provider_isolation.py",
    "scripts/check_paper_strategy_evaluation.py",
    "scripts/check_paper_strategy_sensitivity.py",
    "scripts/check_paper_strategy_robustness.py",
    "scripts/check_paper_strategy_walk_forward.py",
    "scripts/check_paper_strategy_scorecard.py",
    "tests/test_bounded_autonomy_governance.py",
    "tests/test_autonomous_paper_workflow_demo.py",
    "tests/test_paper_provider_isolation.py",
    "tests/test_paper_strategy_evaluation.py",
    "tests/test_paper_strategy_sensitivity.py",
    "tests/test_paper_strategy_robustness.py",
    "tests/test_paper_strategy_walk_forward.py",
    "tests/test_paper_strategy_scorecard.py",
]

REQUIRED_RELEASE_DOCS = [
    "README.md",
    "docs/trust/README.md",
    "docs/public-launch-readiness.md",
    "docs/reviewer-checklist.md",
    "docs/releases/v0.6.13-candidates.md",
    "docs/releases/v0.6.13-candidates.md",
    "docs/releases/v0.6.13-candidates.json",
    "docs/releases/v0.6.13-plan.md",
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
    "v0.6.13 is released",
    "v0.6.13 has been released",
    "v0.6.13 released",
    "current public release: v0.6.13",
    '"current_public_release": "v0.6.13"',
    "tag v0.6.13 created",
    "v0.6.13 tag created",
    "github release v0.6.13 published",
    "v0.6.13 github release created",
    "v0.6.13 pypi publish",
    '"pypi_published": true',
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check v0.6.13 paper-autonomy evidence bundle.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output.")
    parser.add_argument("--root", default=".", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    try:
        result = check(Path(args.root).resolve())
    except Exception as exc:  # pragma: no cover - defensive operational boundary
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

    _check_required_files(root, errors)
    data = _load_evidence_json(json_path, errors)
    if data is not None:
        _check_schema(data, errors)
        _check_candidates(root, data, errors)
        _check_required_references(data, errors)
    _check_markdown(md_path, errors)
    _check_release_metadata(root, errors)
    _check_release_docs(root, errors)

    return _payload(valid=not errors, errors=errors, warnings=warnings)


def _check_required_files(root: Path, errors: list[str]) -> None:
    for rel in [EVIDENCE_MD, EVIDENCE_JSON, *REQUIRED_RELEASE_DOCS]:
        if not (root / rel).exists():
            errors.append(f"Missing required file: {rel}")


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
        "release_line": "v0.6.13",
        "status": "planning_only",
        "current_public_release": "v0.6.12",
        "next_planned_release": "v0.6.13",
        "source_version": "0.6.12",
        "pypi_published": False,
        "v0613_tag_created": False,
        "v0613_github_release_created": False,
    }
    for key, value in expected.items():
        if data.get(key) != value:
            errors.append(f"Evidence JSON {key} must be {value!r}")

    safety = data.get("safety")
    if not isinstance(safety, dict):
        errors.append("Evidence JSON safety must be an object")
        return
    for key in [
        "live_trading_enabled",
        "live_submit_enabled",
        "broker_execution_enabled",
        "provider_execution_enabled_by_default",
        "credentials_or_secrets_added",
        "profit_claims",
        "no_risk_claims",
        "live_readiness_claims",
        "autonomous_live_readiness_claims",
    ]:
        if safety.get(key) is not False:
            errors.append(f"Evidence JSON safety.{key} must be false")

    gate_commands = data.get("gate_commands", [])
    required_commands = [
        "python3.11 scripts/check_v0613_paper_autonomy_evidence.py",
        "python3.11 -m pytest tests/test_v0613_paper_autonomy_evidence.py -q",
    ]
    for command in required_commands:
        if command not in gate_commands:
            errors.append(f"Evidence JSON gate_commands missing: {command}")


def _check_candidates(root: Path, data: dict[str, Any], errors: list[str]) -> None:
    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        errors.append("Evidence JSON candidates must be a list")
        return

    ids = [item.get("id") for item in candidates if isinstance(item, dict)]
    if ids != EXPECTED_CANDIDATES:
        errors.append(f"Evidence JSON candidates must exactly list {EXPECTED_CANDIDATES}")

    for item in candidates:
        if not isinstance(item, dict):
            errors.append("Evidence JSON candidate entries must be objects")
            continue
        candidate_id = item.get("id", "<missing>")
        if item.get("status") != "implemented":
            errors.append(f"{candidate_id} status must be implemented")
        for key in [
            "title",
            "safety_boundary",
            "protected_runtime_boundary_status",
            "release_tag_pypi_status",
            "reviewer_value",
        ]:
            if not item.get(key):
                errors.append(f"{candidate_id} missing required field: {key}")
        for gate_key in ["ci_gate", "dev_gate", "release_quick_gate"]:
            if item.get(gate_key) is not True:
                errors.append(f"{candidate_id} {gate_key} must be true")
        for collection_key in ["primary_docs", "primary_scripts", "primary_tests", "primary_checkers"]:
            value = item.get(collection_key)
            if not isinstance(value, list):
                errors.append(f"{candidate_id} {collection_key} must be a list")
                continue
            for rel in value:
                if not isinstance(rel, str):
                    errors.append(f"{candidate_id} {collection_key} contains a non-string reference")
                    continue
                if not (root / rel).exists():
                    errors.append(f"{candidate_id} references missing file: {rel}")
        if candidate_id != "CAND-021" and not item.get("primary_docs"):
            errors.append(f"{candidate_id} must reference at least one primary doc")
        if candidate_id not in {"CAND-021", "CAND-022"} and not item.get("primary_scripts"):
            errors.append(f"{candidate_id} must reference at least one primary script")
        if not item.get("primary_tests"):
            errors.append(f"{candidate_id} must reference at least one primary test")
        if not item.get("primary_checkers"):
            errors.append(f"{candidate_id} must reference at least one primary checker")


def _check_required_references(data: dict[str, Any], errors: list[str]) -> None:
    candidates = data.get("candidates", [])
    referenced: set[str] = set()
    for item in candidates:
        if not isinstance(item, dict):
            continue
        for key in ["primary_docs", "primary_scripts", "primary_tests", "primary_checkers"]:
            referenced.update(str(rel) for rel in item.get(key, []))
    for rel in REQUIRED_REFERENCES:
        if rel not in referenced:
            errors.append(f"Evidence JSON must reference existing gate artifact: {rel}")


def _check_markdown(path: Path, errors: list[str]) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    lower = text.lower()
    required = [
        "planning only",
        "not financial advice",
        "current public release remains `v0.6.12`",
        "next planned release remains `v0.6.13`",
        "source/package version remains `0.6.12`",
        "cAND-021".lower(),
        "cAND-029".lower(),
        "no `v0.6.13` tag has been created",
        "no `v0.6.13` github release has been created",
        "no `v0.6.13` pypi publication has occurred",
        "live trading remains disabled by default",
        "provider execution remains disabled by default",
        "broker execution remains disabled",
    ]
    for item in required:
        if item not in lower:
            errors.append(f"Evidence Markdown missing required wording: {item}")
    _scan_forbidden_claims(EVIDENCE_MD, text, errors)
    _scan_release_claims(EVIDENCE_MD, text, errors)


def _check_release_metadata(root: Path, errors: list[str]) -> None:
    pyproject = _read(root / "pyproject.toml")
    init_py = _read(root / "src" / "atlas_agent" / "__init__.py")
    metadata_path = root / "docs" / "releases" / "release-metadata.json"
    if not metadata_path.exists():
        errors.append("Missing release metadata: docs/releases/release-metadata.json")
        return
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid release metadata JSON: {exc}")
        return
    posture = (
        metadata.get("source_version"),
        metadata.get("current_public_release"),
        metadata.get("next_planned_release"),
    )
    allowed = {
        ("0.6.13", "v0.6.13", "v0.6.14"),
        ("0.6.14", "v0.6.14", "v0.6.15"),
        ("0.6.15", "v0.6.15", "v0.6.16"),
        ("0.6.16", "v0.6.16", "v0.6.17"),
        ("0.6.17", "v0.6.17", "v0.6.18"),
        ("0.6.18", "v0.6.18", "v0.6.19"),
        ("0.6.19", "v0.6.19", "v0.6.20"),
        ("0.6.20", "v0.6.20", "v0.6.21"),
        ("0.6.21", "v0.6.21", "v0.6.22"),
        ("0.6.24", "v0.6.24", "v0.6.25"),
    }
    if posture not in allowed:
        errors.append(f"release-metadata.json has an unsupported historical posture: {posture!r}")
    if metadata.get("pypi_published") is not False:
        errors.append("release-metadata.json pypi_published must be false")
    active_source = str(metadata.get("source_version", ""))
    if active_source not in pyproject:
        errors.append("pyproject.toml version must match release metadata")
    if active_source not in init_py:
        errors.append("src/atlas_agent/__init__.py version must match release metadata")


def _check_release_docs(root: Path, errors: list[str]) -> None:
    combined = []
    for rel in [EVIDENCE_MD, EVIDENCE_JSON, *REQUIRED_RELEASE_DOCS]:
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        combined.append((rel, text))
        _scan_forbidden_claims(rel, text, errors)
        _scan_release_claims(rel, text, errors)

    inventory_path = root / "docs" / "releases" / "v0.6.13-candidates.json"
    if inventory_path.exists():
        try:
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"Invalid candidate inventory JSON: {exc}")
        else:
            if inventory.get("current_public_release") != "v0.6.12":
                errors.append("Candidate inventory current_public_release must remain v0.6.12")
            if inventory.get("next_planned_release") != "v0.6.13":
                errors.append("Candidate inventory next_planned_release must remain v0.6.13")
            if inventory.get("source_version") != "0.6.12":
                errors.append("Candidate inventory source_version must remain 0.6.12")
            ids = {item.get("id") for item in inventory.get("candidates", []) if isinstance(item, dict)}
            for candidate_id in [*EXPECTED_CANDIDATES, "CAND-030"]:
                if candidate_id not in ids:
                    errors.append(f"Candidate inventory must list {candidate_id}")

    all_text = "\n".join(text for _, text in combined).lower()
    for candidate_id in [*EXPECTED_CANDIDATES, "CAND-030"]:
        if candidate_id.lower() not in all_text:
            errors.append(f"Release docs must mention {candidate_id}")
    if "paper autonomy evidence" not in all_text:
        errors.append("Release docs must mention paper autonomy evidence")


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
                errors.append(f"{rel} contains v0.6.13 release claim without negation: {phrase}")
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
    ]
    return any(negator in window for negator in negators)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _payload(*, valid: bool, errors: list[str], warnings: list[str]) -> dict[str, Any]:
    return {
        "artifact_type": "v0613_paper_autonomy_evidence_check",
        "schema_version": 1,
        "valid": valid,
        "release_line": "v0.6.13",
        "current_public_release": "v0.6.12",
        "next_planned_release": "v0.6.13",
        "source_version": "0.6.12",
        "errors": errors,
        "warnings": warnings,
    }


def _emit(payload: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if payload["valid"]:
        print("v0.6.13 paper-autonomy evidence check PASSED")
        return
    print("v0.6.13 paper-autonomy evidence check FAILED")
    for error in payload["errors"]:
        print(f"  - {error}")


if __name__ == "__main__":
    sys.exit(main())
