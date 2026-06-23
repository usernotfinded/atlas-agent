#!/usr/bin/env python3.11
"""Check the v0.6.15 paper human review evidence bundle and candidate closure gate.

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

ARTIFACT_TYPE = "v0615_paper_human_review_evidence"
CURRENT_PUBLIC = "v0.6.14"
NEXT_PLANNED = "v0.6.15"
SOURCE_VERSION = "0.6.14"
POST_RELEASE_SOURCE_VERSION = "0.6.15"

EVIDENCE_MD = "docs/releases/v0.6.15-paper-human-review-evidence.md"
EVIDENCE_JSON = "docs/releases/v0.6.15-paper-human-review-evidence.json"

EXPECTED_CANDIDATES = [
    "CAND-001",
    "CAND-002",
    "CAND-003",
    "CAND-004",
    "CAND-005",
]

EXPECTED_COMMANDS = [
    "atlas backtest portfolio-review-pack",
    "atlas backtest portfolio-review-ledger",
    "atlas backtest portfolio-review-policy",
    "atlas backtest portfolio-review-replay",
]

EXPECTED_CHECKERS = [
    "scripts/check_paper_human_review_pack.py",
    "scripts/check_paper_human_review_ledger.py",
    "scripts/check_paper_human_review_policy.py",
    "scripts/check_paper_human_review_replay.py",
    "scripts/check_v0615_paper_human_review_evidence.py",
]

EXPECTED_TESTS = [
    "tests/test_paper_human_review_pack.py",
    "tests/test_paper_human_review_ledger.py",
    "tests/test_paper_human_review_policy.py",
    "tests/test_paper_human_review_replay.py",
    "tests/test_v0615_paper_human_review_evidence.py",
]

GATE_FILES = [
    "scripts/dev_check.sh",
    "scripts/ci_check.sh",
    "scripts/release_check.sh",
    ".github/workflows/ci.yml",
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
    "absolute safety",
    "absolutely safe",
    "orders submitted",
    "orders were submitted",
    "order submission",
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
    '"pypi_published": true',
    '"tag_created": true',
    '"github_release_created": true',
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check v0.6.15 paper human review evidence bundle and closure gate."
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

    md_path = root / EVIDENCE_MD
    json_path = root / EVIDENCE_JSON

    _check_required_files(root, md_path, json_path, errors)
    data = _load_evidence_json(json_path, errors)
    if data is not None:
        _check_schema(data, errors)
        _check_candidates(data, errors)
        _check_closure(data, errors)
        _check_evidence_references(root, data, errors)
    _check_markdown(md_path, errors)
    _check_repository_version(root, errors)
    _check_gate_integration(root, errors)

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
        "release": "v0.6.15",
        "release_state": "planning_only",
        "current_public_release": CURRENT_PUBLIC,
        "source_version": SOURCE_VERSION,
        "next_planned_release": NEXT_PLANNED,
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
        "live_path_blocked": True,
        "not_financial_advice": True,
        "not_live_ready": True,
        "closure_decision": "paper_human_review_chain_closed",
    }
    for key, value in expected.items():
        if data.get(key) != value:
            errors.append(f"Evidence JSON {key} must be {value!r}, got {data.get(key)!r}")

    safety = data.get("safety")
    if not isinstance(safety, dict):
        errors.append("Evidence JSON safety must be an object")
        return
    for key in [
        "no_live_trading",
        "no_live_submit",
        "no_broker_calls",
        "no_provider_calls",
        "no_notifications_sent",
        "no_orders_generated",
        "no_real_human_approval",
        "no_profit_claim",
        "no_live_readiness_claim",
        "no_autonomous_live_readiness_claim",
        "no_absolute_safety_claim",
        "no_zero_risk_claim",
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


def _check_closure(data: dict[str, Any], errors: list[str]) -> None:
    if data.get("closure_decision") != "paper_human_review_chain_closed":
        errors.append("Evidence JSON closure_decision must be 'paper_human_review_chain_closed'")


def _check_evidence_references(root: Path, data: dict[str, Any], errors: list[str]) -> None:
    commands = data.get("required_commands", [])
    if not isinstance(commands, list):
        errors.append("Evidence JSON required_commands must be a list")
    elif [cmd for cmd in commands if isinstance(cmd, str)] != EXPECTED_COMMANDS:
        errors.append(f"Evidence JSON required_commands must exactly list {EXPECTED_COMMANDS}")

    for key in ["required_docs", "required_demos", "required_checkers", "required_tests"]:
        values = data.get(key)
        if not isinstance(values, list):
            errors.append(f"Evidence JSON {key} must be a list")
            continue
        for rel in values:
            if not isinstance(rel, str):
                errors.append(f"Evidence JSON {key} contains non-string")
                continue
            path = root / rel
            if not path.exists():
                errors.append(f"Evidence JSON {key} references missing file: {rel}")

            if key == "required_demos" and path.exists():
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
        "current public release: v0.6.14",
        "source/package version: 0.6.14",
        "next planned release: v0.6.15",
        "no tag/release is created",
        "no pypi publication has occurred",
        "paper-only",
        "no provider calls",
        "no broker calls",
        "no real human approval",
        "live path",
        "paper_human_review_chain_closed",
        "not a release cutover",
        "not a live-readiness decision",
    ]
    for item in required:
        if item not in lower:
            errors.append(f"Evidence Markdown missing required wording: {item}")
    _scan_forbidden_claims(EVIDENCE_MD, text, errors)
    _scan_release_claims(EVIDENCE_MD, text, errors)


def _check_repository_version(root: Path, errors: list[str]) -> None:
    """Accept the pre-cutover audited state or the authorized post-cutover state."""
    pyproject = _read(root / "pyproject.toml")
    init_py = _read(root / "src" / "atlas_agent" / "__init__.py")
    source_ok = (
        f'version = "{SOURCE_VERSION}"' in pyproject
        and f'__version__ = "{SOURCE_VERSION}"' in init_py
    ) or (
        f'version = "{POST_RELEASE_SOURCE_VERSION}"' in pyproject
        and f'__version__ = "{POST_RELEASE_SOURCE_VERSION}"' in init_py
    )
    if not source_ok:
        errors.append("Source/package version must match the audited v0.6.15 state (0.6.14 or 0.6.15)")

    release_metadata = _read(root / "docs" / "releases" / "release-metadata.json")
    metadata_ok = (
        '"current_public_release": "v0.6.14"' in release_metadata
        and '"next_planned_release": "v0.6.15"' in release_metadata
    ) or (
        '"current_public_release": "v0.6.15"' in release_metadata
        and '"next_planned_release": "v0.6.16"' in release_metadata
    )
    if not metadata_ok:
        errors.append("Release metadata must match the audited v0.6.15 state")
    if '"pypi_published": false' not in release_metadata:
        errors.append("Release metadata pypi_published must remain false")


def _check_gate_integration(root: Path, errors: list[str]) -> None:
    for gate_file in GATE_FILES:
        path = root / gate_file
        if not path.exists():
            errors.append(f"Gate file missing: {gate_file}")
            continue
        content = path.read_text(encoding="utf-8")
        for checker in EXPECTED_CHECKERS:
            name = Path(checker).name
            if name not in content:
                errors.append(f"Gate file {gate_file} does not reference {checker}")
        for test in EXPECTED_TESTS:
            name = Path(test).name
            if name not in content:
                errors.append(f"Gate file {gate_file} does not reference {test}")


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
                errors.append(f"{rel} contains v0.6.15 release claim without negation: {phrase}")
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
        "artifact_type": "v0615_paper_human_review_evidence_check",
        "schema_version": 1,
        "valid": valid,
        "release": "v0.6.15",
        "current_public_release": CURRENT_PUBLIC,
        "source_version": SOURCE_VERSION,
        "next_planned_release": NEXT_PLANNED,
        "errors": errors,
        "warnings": warnings,
    }


def _emit(payload: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if payload["valid"]:
        print("v0.6.15 paper human review evidence check PASSED")
        return
    print("v0.6.15 paper human review evidence check FAILED")
    for error in payload["errors"]:
        print(f"  - {error}")


if __name__ == "__main__":
    sys.exit(main())
