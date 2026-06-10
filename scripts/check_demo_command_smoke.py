#!/usr/bin/env python3
"""Lightweight static smoke checker for the demo command surface (CAND-004).

Validates that the demo script exists, is executable, is referenced in key docs,
contains expected safe-command wording, and excludes forbidden high-risk patterns.
Static, read-only, no execution, no network, no credentials.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

DEMO_SCRIPT = REPO_ROOT / "scripts" / "demo_paper_workflow.sh"
CHECK_DEMO_PROOF = REPO_ROOT / "scripts" / "check_demo_proof.py"
ARTIFACT_INDEX = REPO_ROOT / "docs" / "demo-artifact-index.md"
PAPER_WORKFLOW_DOC = REPO_ROOT / "docs" / "demo-paper-workflow.md"
EXTERNAL_REVIEWER_DOC = REPO_ROOT / "docs" / "external-reviewer-walkthrough.md"
README = REPO_ROOT / "README.md"
CANDIDATES_MD = REPO_ROOT / "docs" / "releases" / "v0.6.8-candidates.md"
CANDIDATES_JSON = REPO_ROOT / "docs" / "releases" / "v0.6.8-candidates.json"

CANONICAL_COMMAND = "./scripts/demo_paper_workflow.sh"

FORBIDDEN_PATTERNS = [
    "curl ",
    "wget ",
    "twine" + " upload",
    "gh release create",
    "git push --tags",
    "git push --force",
    "git tag",
    "git reset --hard",
    "git clean",
    "ALPACA",
    "BINANCE",
    "CCXT",
    "IBKR",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "submit order",
    "enable live trading",
    "rm -rf",
    "--mode live",
]

PAPER_WORDING = ("--mode paper", "--dry-run", "paper-only")


def _read(path: Path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _check_script_exists() -> list[str]:
    violations: list[str] = []
    if not DEMO_SCRIPT.exists():
        violations.append(f"Demo script not found: {DEMO_SCRIPT.relative_to(REPO_ROOT)}")
    elif not os.access(DEMO_SCRIPT, os.X_OK):
        violations.append(f"Demo script is not executable: {DEMO_SCRIPT.relative_to(REPO_ROOT)}")
    return violations


def _check_canonical_command_references() -> list[str]:
    violations: list[str] = []
    for path in (README, EXTERNAL_REVIEWER_DOC, PAPER_WORKFLOW_DOC):
        if not path.exists():
            violations.append(f"Doc not found: {path.name}")
            continue
        if CANONICAL_COMMAND not in _read(path):
            violations.append(f"Doc missing canonical command '{CANONICAL_COMMAND}': {path.name}")
    return violations


def _check_demo_proof_references() -> list[str]:
    violations: list[str] = []
    if not CHECK_DEMO_PROOF.exists():
        violations.append(f"Demo proof checker not found: {CHECK_DEMO_PROOF.relative_to(REPO_ROOT)}")

    for path in (EXTERNAL_REVIEWER_DOC, PAPER_WORKFLOW_DOC, ARTIFACT_INDEX):
        if not path.exists():
            violations.append(f"Doc not found: {path.name}")
            continue
        if "check_demo_proof.py" not in _read(path):
            violations.append(f"Doc missing reference to check_demo_proof.py: {path.name}")
    return violations


def _check_artifact_index_references() -> list[str]:
    violations: list[str] = []
    if not ARTIFACT_INDEX.exists():
        violations.append(f"Artifact index not found: {ARTIFACT_INDEX.relative_to(REPO_ROOT)}")

    for path in (README, EXTERNAL_REVIEWER_DOC, PAPER_WORKFLOW_DOC):
        if not path.exists():
            violations.append(f"Doc not found: {path.name}")
            continue
        if "demo-artifact-index.md" not in _read(path):
            violations.append(f"Doc missing reference to demo-artifact-index.md: {path.name}")
    return violations


def _check_forbidden_patterns(text: str) -> list[str]:
    violations: list[str] = []
    for pattern in FORBIDDEN_PATTERNS:
        if pattern in text:
            violations.append(f"Demo script contains forbidden pattern: {pattern}")
    return violations


def _check_paper_wording(text: str) -> list[str]:
    violations: list[str] = []
    if not any(phrase in text for phrase in PAPER_WORDING):
        violations.append(
            "Demo script missing paper/local safety wording "
            "(--mode paper, --dry-run, or paper-only)"
        )
    return violations


def _check_candidates_md_state(text: str) -> list[str]:
    violations: list[str] = []
    in_accepted = False
    for line in text.splitlines():
        if "## Accepted Candidates" in line:
            in_accepted = True
        elif line.startswith("## "):
            in_accepted = False
        if in_accepted:
            for cand_id in ("CAND-001", "CAND-002", "CAND-003", "CAND-004"):
                if cand_id in line:
                    if "not yet implemented" in line.lower():
                        violations.append(f"{line.strip()} should be marked implemented")
                    elif "implemented" not in line.lower():
                        violations.append(f"{line.strip()} not marked implemented")
    return violations


def _check_candidates_json_state(data: dict) -> list[str]:
    violations: list[str] = []
    candidates = {c["id"]: c for c in data.get("candidates", [])}
    for cand_id in ("CAND-001", "CAND-002", "CAND-003", "CAND-004"):
        if cand_id not in candidates:
            violations.append(f"{cand_id} missing from candidates JSON")
    for cand_id in ("CAND-001", "CAND-002", "CAND-003", "CAND-004"):
        if cand_id in candidates and candidates[cand_id].get("implemented") is not True:
            violations.append(f"{cand_id} not marked implemented=true in candidates JSON")
    return violations


def main() -> int:
    violations: list[str] = []

    # Script surface
    violations.extend(_check_script_exists())
    script_text = _read(DEMO_SCRIPT) if DEMO_SCRIPT.exists() else ""
    if script_text:
        violations.extend(_check_forbidden_patterns(script_text))
        violations.extend(_check_paper_wording(script_text))

    # Doc cross-references
    violations.extend(_check_canonical_command_references())
    violations.extend(_check_demo_proof_references())
    violations.extend(_check_artifact_index_references())

    # Candidate tracking
    if CANDIDATES_MD.exists():
        violations.extend(_check_candidates_md_state(_read(CANDIDATES_MD)))
    else:
        violations.append("Candidates markdown not found")

    if CANDIDATES_JSON.exists():
        try:
            data = json.loads(_read(CANDIDATES_JSON))
            violations.extend(_check_candidates_json_state(data))
        except json.JSONDecodeError as exc:
            violations.append(f"Candidates JSON invalid: {exc}")
    else:
        violations.append("Candidates JSON not found")

    if violations:
        print("Demo command smoke check FAILED")
        for v in violations:
            print(f"  - {v}")
        return 1

    print("Demo command smoke check PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
