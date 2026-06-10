#!/usr/bin/env python3
"""Deterministic demo proof checker for CAND-002 and CAND-003.

Validates demo documentation, artifact index consistency, safety invariants,
script/doc alignment, canonical reviewer path, symbol consistency, and
over-promise claims. Local-only; no credentials, network, or execution.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent

DEMO_SCRIPT = REPO_ROOT / "scripts" / "demo_paper_workflow.sh"
ARTIFACT_INDEX = REPO_ROOT / "docs" / "demo-artifact-index.md"
PAPER_WORKFLOW_DOC = REPO_ROOT / "docs" / "demo-paper-workflow.md"
EXTERNAL_REVIEWER_DOC = REPO_ROOT / "docs" / "external-reviewer-walkthrough.md"
README = REPO_ROOT / "README.md"
TRUST_README = REPO_ROOT / "docs" / "trust" / "README.md"
BROKERS_DOC = REPO_ROOT / "docs" / "brokers.md"
CANDIDATES_MD = REPO_ROOT / "docs" / "releases" / "v0.6.8-candidates.md"
CANDIDATES_JSON = REPO_ROOT / "docs" / "releases" / "v0.6.8-candidates.json"

DEMO_SURFACES = [
    README,
    PAPER_WORKFLOW_DOC,
    EXTERNAL_REVIEWER_DOC,
    ARTIFACT_INDEX,
    DEMO_SCRIPT,
]

LINKING_DOCS = [README, PAPER_WORKFLOW_DOC, EXTERNAL_REVIEWER_DOC]

REQUIRED_SCRIPT_COMMANDS = [
    "mktemp -d",
    "ATLAS-DEMO",
    "DEMO-SYMBOL",
    "discipline setup --manual --yes",
    "validate",
    "run --mode paper --dry-run",
    "backtest run",
    "audit verify --all",
]

FORBIDDEN_SCRIPT_PHRASES = [
    "rm -rf",
    "set_secret",
    ".env.atlas",
    "enable_live_trading",
    "--mode live",
    "curl ",
    "git ",
]

FORBIDDEN_POSITIVE_CLAIMS = [
    "live trading ready",
    "production trading ready",
    "safe to trade",
    "trust granted",
    "provider execution enabled",
    "broker execution enabled",
    "orders enabled",
    "approvals enabled",
    "autonomous trading ready",
    "guaranteed profit",
    "profitable strategy",
    "verified alpha",
    "beats the market",
    "real-money ready",
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
)

REQUIRED_INDEX_SECTIONS = [
    "## Purpose",
    "## Safety Scope",
    "## Demo Command",
    "## Artifact Summary",
    "## Artifact Details",
    "## Success Criteria",
    "## Troubleshooting",
    "## Related Docs",
]

REQUIRED_SAFETY_CLAIMS = [
    "Paper/local only",
    "No live broker credentials required",
    "No provider API keys required",
    "No live orders submitted",
    "No provider execution unlocked",
    "No broker execution unlocked",
    "No financial advice",
    "No autonomous trading claim",
]

SECRET_PATTERNS = [
    r"\b[A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD)[A-Z0-9_]*\s*=\s*(?!\[REDACTED\])\S+",
    r"\bYOUR_[A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD)[A-Z0-9_]*\b",
    r"\b(?:sk-|pplx-|xox[baprs]-|AKIA)[A-Za-z0-9_-]{10,}\b",
]

EXPECTED_ARTIFACT_PATHS = [
    ".atlas/config.toml",
    ".atlas/discipline.md",
    "result.json",
    "report.md",
    "audit/",
    "pending_orders/",
]

STALE_OVER_PROMISE_PATTERNS = [
    # (pattern, description)
    (r"source version on main is prepared", "stale source-version-prepared claim"),
    (r"prepared v0\.6\.8 release notes", "stale v0.6.8 release-notes-prepared claim"),
    (r"prepared v0\.6\.8.*status documentation", "stale v0.6.8 status-docs-prepared claim"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _sentence_around(text: str, start: int, end: int) -> str:
    """Extract the sentence/paragraph containing the match."""
    boundary_chars = {".", "!", "?", "\n"}
    s = start
    while s > 0 and text[s - 1] not in boundary_chars:
        s -= 1
    e = end
    while e < len(text) and text[e] not in boundary_chars:
        e += 1
    return text[s:e]


# ---------------------------------------------------------------------------
# Check functions (each returns list[str] of violations)
# ---------------------------------------------------------------------------

def _check_script_exists() -> list[str]:
    violations: list[str] = []
    if not DEMO_SCRIPT.exists():
        violations.append("Demo script not found: scripts/demo_paper_workflow.sh")
    elif not os.access(DEMO_SCRIPT, os.X_OK):
        violations.append("Demo script is not executable: scripts/demo_paper_workflow.sh")
    return violations


def _check_script_shebang_and_flags(text: str) -> list[str]:
    violations: list[str] = []
    if not text.startswith("#!/usr/bin/env bash\nset -euo pipefail\n"):
        violations.append("Demo script missing safe shebang or set flags")
    return violations


def _check_script_required_commands(text: str) -> list[str]:
    violations: list[str] = []
    for cmd in REQUIRED_SCRIPT_COMMANDS:
        if cmd not in text:
            violations.append(f"Demo script missing expected command: {cmd}")
    return violations


def _check_script_forbidden_phrases(text: str) -> list[str]:
    violations: list[str] = []
    for phrase in FORBIDDEN_SCRIPT_PHRASES:
        if phrase in text:
            violations.append(f"Demo script contains forbidden phrase: {phrase}")
    return violations


def _check_index_required_sections(text: str) -> list[str]:
    violations: list[str] = []
    for section in REQUIRED_INDEX_SECTIONS:
        if section not in text:
            violations.append(f"Artifact index missing required section: {section}")
    return violations


def _check_index_safety_claims(text: str) -> list[str]:
    violations: list[str] = []
    for claim in REQUIRED_SAFETY_CLAIMS:
        if claim not in text:
            violations.append(f"Artifact index missing safety claim: {claim}")
    return violations


def _check_index_artifacts_documented(text: str) -> list[str]:
    violations: list[str] = []
    for path in EXPECTED_ARTIFACT_PATHS:
        if path not in text:
            violations.append(f"Artifact index missing expected artifact path: {path}")
    return violations


def _check_index_links(text: str) -> list[str]:
    violations: list[str] = []
    required_links = [
        "[Demo: Paper Workflow](demo-paper-workflow.md)",
        "[External Reviewer Walkthrough](external-reviewer-walkthrough.md)",
    ]
    for link in required_links:
        if link not in text:
            violations.append(f"Artifact index missing required link: {link}")
    return violations


def _check_linking_docs_reference_index() -> list[str]:
    violations: list[str] = []
    for path in LINKING_DOCS:
        if not path.exists():
            violations.append(f"Linking doc not found: {path}")
            continue
        text = _read(path)
        if "demo-artifact-index.md" not in text:
            violations.append(f"Linking doc does not reference artifact index: {path.name}")
    return violations


def _check_docs_mention_script() -> list[str]:
    violations: list[str] = []
    for path in [README, PAPER_WORKFLOW_DOC, EXTERNAL_REVIEWER_DOC, ARTIFACT_INDEX]:
        if not path.exists():
            violations.append(f"Doc not found: {path.name}")
            continue
        text = _read(path)
        if "demo_paper_workflow.sh" not in text:
            violations.append(f"Doc does not mention demo script: {path.name}")
    return violations


def _check_canonical_reviewer_path() -> list[str]:
    """Validate that the canonical reviewer path is linked across docs."""
    violations: list[str] = []

    # README must link to external reviewer walkthrough
    readme_text = _read(README) if README.exists() else ""
    if "external-reviewer-walkthrough.md" not in readme_text:
        violations.append("README missing link to external-reviewer-walkthrough.md")

    # External reviewer walkthrough must link to paper workflow and artifact index
    reviewer_text = _read(EXTERNAL_REVIEWER_DOC) if EXTERNAL_REVIEWER_DOC.exists() else ""
    if "demo-paper-workflow.md" not in reviewer_text:
        violations.append("External reviewer walkthrough missing link to demo-paper-workflow.md")
    if "demo-artifact-index.md" not in reviewer_text:
        violations.append("External reviewer walkthrough missing link to demo-artifact-index.md")
    if "check_demo_proof.py" not in reviewer_text:
        violations.append("External reviewer walkthrough missing link to check_demo_proof.py")

    # Paper workflow doc must link to external reviewer walkthrough and artifact index
    paper_text = _read(PAPER_WORKFLOW_DOC) if PAPER_WORKFLOW_DOC.exists() else ""
    if "external-reviewer-walkthrough.md" not in paper_text:
        violations.append("Demo paper workflow doc missing link to external-reviewer-walkthrough.md")
    if "demo-artifact-index.md" not in paper_text:
        violations.append("Demo paper workflow doc missing link to demo-artifact-index.md")

    return violations


def _check_demo_surfaces_forbidden_claims() -> list[str]:
    violations: list[str] = []
    for path in DEMO_SURFACES:
        if not path.exists():
            continue
        text = _read(path).lower()
        for phrase in FORBIDDEN_POSITIVE_CLAIMS:
            for m in re.finditer(re.escape(phrase), text):
                sentence = _sentence_around(text, m.start(), m.end()).lower()
                if not any(ind in sentence for ind in NEGATIVE_CONTEXT_INDICATORS):
                    violations.append(
                        f"[{path.name}] Forbidden positive claim '{phrase}' outside negative context"
                    )
    return violations


def _check_demo_surfaces_secrets() -> list[str]:
    violations: list[str] = []
    for path in DEMO_SURFACES:
        if not path.exists():
            continue
        text = _read(path)
        for pattern in SECRET_PATTERNS:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                violations.append(
                    f"[{path.name}] Secret-like pattern matched: {m.group(0)[:40]}"
                )
    return violations


def _check_symbol_consistency() -> list[str]:
    """Verify core demo symbols appear where expected and README is consistent."""
    violations: list[str] = []
    script_text = _read(DEMO_SCRIPT) if DEMO_SCRIPT.exists() else ""
    index_text = _read(ARTIFACT_INDEX) if ARTIFACT_INDEX.exists() else ""
    paper_text = _read(PAPER_WORKFLOW_DOC) if PAPER_WORKFLOW_DOC.exists() else ""
    readme_text = _read(README) if README.exists() else ""

    if "ATLAS-DEMO" not in script_text:
        violations.append("Demo script missing ATLAS-DEMO symbol")
    if "DEMO-SYMBOL" not in script_text:
        violations.append("Demo script missing DEMO-SYMBOL symbol")
    if "ATLAS-DEMO" not in index_text:
        violations.append("Artifact index missing ATLAS-DEMO symbol")
    if "DEMO-SYMBOL" not in paper_text:
        violations.append("Demo paper workflow doc missing DEMO-SYMBOL symbol")
    if "ATLAS-DEMO" not in paper_text:
        violations.append("Demo paper workflow doc missing ATLAS-DEMO symbol")

    # CAND-003: README must use ATLAS-DEMO for the config symbol, not DEMO-SYMBOL
    # We look for the config set line and ensure it uses ATLAS-DEMO
    readme_lines = readme_text.splitlines()
    for line in readme_lines:
        if "config set market.symbol" in line:
            if "ATLAS-DEMO" not in line:
                violations.append(
                    "README config set market.symbol does not use ATLAS-DEMO"
                )
            break
    else:
        violations.append("README missing config set market.symbol line")

    return violations


def _check_stale_over_promise_claims() -> list[str]:
    """Detect stale or over-promise claims in public-facing docs.

    CAND-003 specifically fixed:
    - README claiming 0.6.8 source is prepared
    - trust/README claiming v0.6.8 release notes are prepared
    - brokers.md calling PaperBroker production-ready
    """
    violations: list[str] = []

    # Check README for stale source-version claims
    readme_text = _read(README) if README.exists() else ""
    for pattern, desc in STALE_OVER_PROMISE_PATTERNS:
        if re.search(pattern, readme_text, re.IGNORECASE):
            violations.append(f"README contains stale/over-promise claim: {desc}")

    # Check trust/README for stale v0.6.8 claims
    trust_text = _read(TRUST_README) if TRUST_README.exists() else ""
    for pattern, desc in STALE_OVER_PROMISE_PATTERNS:
        if re.search(pattern, trust_text, re.IGNORECASE):
            violations.append(f"docs/trust/README.md contains stale/over-promise claim: {desc}")

    # Check brokers.md for "production-ready" in positive context
    brokers_text = _read(BROKERS_DOC) if BROKERS_DOC.exists() else ""
    if "production-ready" in brokers_text.lower():
        # Verify it's in a negative/safe context
        for m in re.finditer(r"production-ready", brokers_text, re.IGNORECASE):
            sentence = _sentence_around(brokers_text, m.start(), m.end()).lower()
            if not any(ind in sentence for ind in NEGATIVE_CONTEXT_INDICATORS):
                violations.append(
                    "docs/brokers.md contains 'production-ready' outside negative context"
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
            if "CAND-001" in line or "CAND-002" in line or "CAND-003" in line:
                if "not yet implemented" in line.lower():
                    violations.append(f"{line.strip()} should be marked implemented in candidates markdown")
                elif "implemented" not in line.lower():
                    violations.append(f"{line.strip()} not marked implemented in candidates markdown")
            if "CAND-004" in line:
                if "not yet implemented" not in line.lower():
                    violations.append(
                        f"{line.strip()} should be marked not yet implemented in candidates markdown"
                    )
    return violations


def _check_candidates_json_state(data: dict) -> list[str]:
    violations: list[str] = []
    candidates = {c["id"]: c for c in data.get("candidates", [])}
    for cand_id in ("CAND-001", "CAND-002", "CAND-003", "CAND-004"):
        if cand_id not in candidates:
            violations.append(f"{cand_id} missing from candidates JSON")
    for cand_id in ("CAND-001", "CAND-002", "CAND-003"):
        if cand_id in candidates and candidates[cand_id].get("implemented") is not True:
            violations.append(f"{cand_id} not marked implemented=true in candidates JSON")
    for cand_id in ("CAND-004",):
        if cand_id in candidates and candidates[cand_id].get("implemented") is not False:
            violations.append(f"{cand_id} not marked implemented=false in candidates JSON")
    return violations


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    all_violations: list[str] = []
    all_warnings: list[str] = []

    # Script checks
    script_text = _read(DEMO_SCRIPT) if DEMO_SCRIPT.exists() else ""
    all_violations.extend(_check_script_exists())
    if script_text:
        all_violations.extend(_check_script_shebang_and_flags(script_text))
        all_violations.extend(_check_script_required_commands(script_text))
        all_violations.extend(_check_script_forbidden_phrases(script_text))

    # Artifact index checks
    index_text = _read(ARTIFACT_INDEX) if ARTIFACT_INDEX.exists() else ""
    if index_text:
        all_violations.extend(_check_index_required_sections(index_text))
        all_violations.extend(_check_index_safety_claims(index_text))
        all_violations.extend(_check_index_artifacts_documented(index_text))
        all_violations.extend(_check_index_links(index_text))

    # Cross-link checks
    all_violations.extend(_check_linking_docs_reference_index())
    all_violations.extend(_check_docs_mention_script())
    all_violations.extend(_check_canonical_reviewer_path())

    # Demo surface checks
    all_violations.extend(_check_demo_surfaces_forbidden_claims())
    all_violations.extend(_check_demo_surfaces_secrets())

    # Symbol consistency
    all_violations.extend(_check_symbol_consistency())

    # Stale/over-promise claims (CAND-003)
    all_violations.extend(_check_stale_over_promise_claims())

    # Candidate tracking
    candidates_md_text = _read(CANDIDATES_MD) if CANDIDATES_MD.exists() else ""
    if candidates_md_text:
        all_violations.extend(_check_candidates_md_state(candidates_md_text))

    if CANDIDATES_JSON.exists():
        candidates_data = json.loads(_read(CANDIDATES_JSON))
        all_violations.extend(_check_candidates_json_state(candidates_data))

    if all_violations:
        print("Demo proof check FAILED")
        for v in all_violations:
            print(f"  - {v}")
        if all_warnings:
            for w in all_warnings:
                print(f"  WARN: {w}")
        return 1

    print("Demo proof check PASSED")
    if all_warnings:
        for w in all_warnings:
            print(f"  WARN: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
