#!/usr/bin/env python3
"""Check the CAND-027 paper strategy robustness surface.

Deterministic and local-only. Does not mutate files, call providers, call
brokers, access credentials, run network operations, tag, release, or publish.

Exit codes:
  0 = pass
  1 = findings
  2 = operational error
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


CURRENT_PUBLIC = "v0.6.12"
NEXT_PLANNED = "v0.6.13"
SOURCE_VERSION = "0.6.12"

REQUIRED_DOCS = [
    "docs/paper-strategy-robustness.md",
    "docs/paper-strategy-evaluation.md",
    "docs/paper-strategy-sensitivity.md",
    "docs/paper-provider-isolation.md",
    "docs/autonomous-paper-workflow.md",
    "docs/bounded-live-autonomy-governance.md",
]
RELATIONSHIP_DOCS = [
    "docs/autonomy-roadmap.md",
    "docs/public-launch-readiness.md",
    "docs/reviewer-checklist.md",
    "docs/trust/README.md",
    "docs/releases/v0.6.13-candidate-selection.md",
    "docs/releases/v0.6.13-candidates.md",
    "docs/releases/v0.6.13-candidates.json",
    "docs/releases/v0.6.13-plan.md",
]
REGIME_FIXTURES = [
    "data/sample/regimes/ohlcv_uptrend.csv",
    "data/sample/regimes/ohlcv_downtrend.csv",
    "data/sample/regimes/ohlcv_flat.csv",
    "data/sample/regimes/ohlcv_volatile.csv",
]
ALLOWED_DECISIONS = {
    "robust_paper_follow_up",
    "regime_sensitive_needs_more_testing",
    "needs_more_testing",
    "rejected",
}
FORBIDDEN_DECISIONS = {
    "live_ready",
    "production_ready",
    "safe_to_trade_live",
    "approved_for_live",
    "guaranteed_profit",
    "outperforms_market",
}
FORBIDDEN_DOC_CLAIMS = [
    "guaranteed profit",
    "risk-free",
    "zero risk",
    "no-risk",
    "safe live trading",
    "ready for live",
    "live ready",
    "outperforms the market",
    "will outperform",
    "approved for live",
]
DEMO_FORBIDDEN = [
    "--mode live",
    "twine" + " upload",
    "git tag",
    "gh release create",
    "pypi",
    "curl ",
    "wget ",
]
PROVIDER_OR_BROKER_CALL_HINTS = [
    "openai ",
    "anthropic ",
    "openrouter ",
    "alpaca",
    "binance",
    "place_order",
    "submit_order",
]
REQUIRED_DOC_TOPICS = [
    "paper-only",
    "offline",
    "no-provider",
    "no-broker",
    "no-network",
    "not financial advice",
    "no profit guarantee",
    "not live-readiness",
    "robust_paper_follow_up",
    "regime_sensitive_needs_more_testing",
    "needs_more_testing",
    "rejected",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Emit machine-readable result.")
    parser.add_argument("--root", default=".", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    try:
        result = check(Path(args.root).resolve())
    except Exception as exc:
        payload = _payload(valid=False, errors=[f"Operational error: {exc}"])
        _emit(payload, json_output=args.json)
        return 2

    _emit(result, json_output=args.json)
    return 0 if result["valid"] else 1


def check(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    _check_required_files(root, errors)
    _check_fixtures(root, errors)
    _check_demo_script(root, errors)
    _check_docs(root, errors)
    _check_release_metadata(root, errors)
    _check_candidate_docs(root, errors, warnings)

    return _payload(valid=not errors, errors=errors, warnings=warnings)


def _check_required_files(root: Path, errors: list[str]) -> None:
    for rel in REQUIRED_DOCS + RELATIONSHIP_DOCS:
        if not (root / rel).exists():
            errors.append(f"Missing required file: {rel}")
    demo = root / "scripts" / "demo_paper_strategy_robustness.sh"
    checker = root / "scripts" / "check_paper_strategy_robustness.py"
    if not demo.exists():
        errors.append("Missing demo script: scripts/demo_paper_strategy_robustness.sh")
    if not checker.exists():
        errors.append("Missing checker: scripts/check_paper_strategy_robustness.py")


def _check_fixtures(root: Path, errors: list[str]) -> None:
    expected_header = ["timestamp", "open", "high", "low", "close", "volume"]
    for rel in REGIME_FIXTURES:
        path = root / rel
        if not path.exists():
            errors.append(f"Missing deterministic regime fixture: {rel}")
            continue
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
        except OSError as exc:
            errors.append(f"Cannot read fixture {rel}: {exc}")
            continue
        if not rows or rows[0] != expected_header:
            errors.append(f"Fixture {rel} must have OHLCV header {expected_header}")
            continue
        if len(rows) - 1 < 90:
            errors.append(f"Fixture {rel} must contain at least 90 sample rows")


def _check_demo_script(root: Path, errors: list[str]) -> None:
    path = root / "scripts" / "demo_paper_strategy_robustness.sh"
    if not path.exists():
        return
    if not os.access(path, os.X_OK):
        errors.append("Demo script must be executable")
    text = _read(path)
    lower = text.lower()
    required = [
        "set -euo pipefail",
        "backtest robustness",
        "strategy-robustness.json",
        "strategy-robustness.md",
        "data/sample/regimes/ohlcv_uptrend.csv",
        "data/sample/regimes/ohlcv_downtrend.csv",
        "data/sample/regimes/ohlcv_flat.csv",
        "data/sample/regimes/ohlcv_volatile.csv",
        "demo-symbol",
    ]
    for item in required:
        if item not in lower:
            errors.append(f"Demo script missing required content: {item}")
    for item in DEMO_FORBIDDEN + PROVIDER_OR_BROKER_CALL_HINTS:
        if item in lower:
            errors.append(f"Demo script contains forbidden operation or integration hint: {item.strip()}")
    if "api_key" in lower and "export " not in lower:
        errors.append("Demo script must not reference credential values")
    if "strategy-sensitivity" in lower:
        errors.append("Demo script must run the robustness command, not sensitivity output checks")


def _check_docs(root: Path, errors: list[str]) -> None:
    doc = root / "docs" / "paper-strategy-robustness.md"
    if not doc.exists():
        return
    text = _read(doc)
    lower = text.lower()
    for topic in REQUIRED_DOC_TOPICS:
        if topic not in lower:
            errors.append(f"Robustness doc missing required topic: {topic}")
    for decision in ALLOWED_DECISIONS:
        if decision not in text:
            errors.append(f"Robustness doc missing allowed decision: {decision}")
    for decision in FORBIDDEN_DECISIONS:
        if decision in text:
            errors.append(f"Robustness doc contains forbidden decision: {decision}")
    for claim in FORBIDDEN_DOC_CLAIMS:
        for match in re.finditer(re.escape(claim), lower):
            if not _is_negated(lower, match.start()):
                errors.append(f"Forbidden robustness doc claim: {claim}")
                break
    required_links = [
        "paper-strategy-evaluation.md",
        "paper-strategy-sensitivity.md",
        "autonomous-paper-workflow.md",
        "paper-provider-isolation.md",
        "bounded-live-autonomy-governance.md",
        "live-submit-safety-contract.md",
    ]
    for link in required_links:
        if link not in lower:
            errors.append(f"Robustness doc missing relationship link: {link}")


def _check_release_metadata(root: Path, errors: list[str]) -> None:
    pyproject = _read(root / "pyproject.toml")
    init_py = _read(root / "src" / "atlas_agent" / "__init__.py")
    metadata_path = root / "docs" / "releases" / "release-metadata.json"
    if SOURCE_VERSION not in pyproject:
        errors.append("Source/package version must remain 0.6.12 in pyproject.toml")
    if SOURCE_VERSION not in init_py:
        errors.append("Source/package version must remain 0.6.12 in src/atlas_agent/__init__.py")
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"Invalid release metadata JSON: {exc}")
            return
        checks = {
            "source_version": SOURCE_VERSION,
            "current_public_release": CURRENT_PUBLIC,
            "next_planned_release": NEXT_PLANNED,
            "pypi_published": False,
        }
        for key, expected in checks.items():
            if metadata.get(key) != expected:
                errors.append(f"release-metadata.json {key} must be {expected!r}")
    else:
        errors.append("Missing release metadata: docs/releases/release-metadata.json")


def _check_candidate_docs(root: Path, errors: list[str], warnings: list[str]) -> None:
    candidate_paths = [
        root / "docs" / "releases" / "v0.6.13-candidate-selection.md",
        root / "docs" / "releases" / "v0.6.13-candidates.md",
        root / "docs" / "releases" / "v0.6.13-plan.md",
    ]
    combined = "\n".join(_read(path) for path in candidate_paths)
    lower = combined.lower()
    if "cand-027" not in lower:
        errors.append("CAND-027 must be listed in v0.6.13 candidate planning docs")
    if "paper strategy robustness" not in lower:
        errors.append("Candidate docs must mention paper strategy robustness")
    for phrase in [
        "v0.6.13 is released",
        "v0.6.13 has been released",
        "current public release v0.6.13",
        "github release v0.6.13 published",
        "tag v0.6.13 created",
    ]:
        for match in re.finditer(re.escape(phrase), lower):
            if not _is_negated(lower, match.start()):
                errors.append(f"Candidate docs claim v0.6.13 release state: {phrase}")
                break

    inventory_path = root / "docs" / "releases" / "v0.6.13-candidates.json"
    if not inventory_path.exists():
        return
    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid candidate inventory JSON: {exc}")
        return
    if inventory.get("current_public_release") != CURRENT_PUBLIC:
        errors.append("Candidate inventory current_public_release must remain v0.6.12")
    if inventory.get("next_planned_release") != NEXT_PLANNED:
        errors.append("Candidate inventory next_planned_release must remain v0.6.13")
    if inventory.get("source_version") != SOURCE_VERSION:
        errors.append("Candidate inventory source_version must remain 0.6.12")
    if inventory.get("status") != "planning":
        errors.append("Candidate inventory status must remain planning")
    candidates = inventory.get("candidates", [])
    if not any(item.get("id") == "CAND-027" and item.get("implemented") is True for item in candidates):
        errors.append("Candidate inventory must list implemented CAND-027")
    if not candidates:
        warnings.append("Candidate inventory has no candidates")


def _is_negated(text: str, index: int, window: int = 80) -> bool:
    prefix = text[max(0, index - window) : index]
    return any(
        hint in prefix
        for hint in (
            "no ",
            "not ",
            "never ",
            "does not ",
            "do not ",
            "must not ",
            "without ",
            "absent ",
            "disabled ",
        )
    )


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _payload(*, valid: bool, errors: list[str], warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "artifact_type": "paper_strategy_robustness_check",
        "schema_version": 1,
        "valid": valid,
        "status": "pass" if valid else "fail",
        "errors": errors,
        "warnings": warnings or [],
        "safety": {
            "local_only": True,
            "no_network": True,
            "no_provider_calls": True,
            "no_broker_calls": True,
            "no_file_mutation": True,
        },
    }


def _emit(payload: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if payload["valid"]:
        print("Paper strategy robustness check PASSED")
        return
    print("Paper strategy robustness check FAILED")
    for error in payload["errors"]:
        print(f"  - {error}")
    for warning in payload.get("warnings", []):
        print(f"  - warning: {warning}")


if __name__ == "__main__":
    sys.exit(main())
