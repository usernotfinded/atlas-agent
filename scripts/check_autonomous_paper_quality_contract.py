from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC = REPO_ROOT / "docs" / "autonomous-paper-quality-gate.md"
GOVERNANCE_DOC = REPO_ROOT / "docs" / "bounded-live-autonomy-governance.md"
SHADOW_DOC = REPO_ROOT / "docs" / "shadow-live-readiness-contract.md"
MODULES = [REPO_ROOT / "src" / "atlas_agent" / "agent" / "autonomous_paper_quality.py"]
CLI_MODULE = REPO_ROOT / "src" / "atlas_agent" / "cli.py"
TEST_MODULE = REPO_ROOT / "tests" / "test_autonomous_paper_quality.py"
CONTRACT_TEST_MODULE = REPO_ROOT / "tests" / "test_autonomous_paper_quality_contract.py"

REQUIRED_FILES = [DOC, GOVERNANCE_DOC, SHADOW_DOC, *MODULES, CLI_MODULE, TEST_MODULE, CONTRACT_TEST_MODULE]

REQUIRED_DOC_PHRASES = (
    "paper-only",
    "no live trading",
    "RiskManager",
    "not financial advice",
    "does **not** claim autonomous live trading readiness",
    "deterministic",
    "offline",
    "atlas agent autonomous-paper-quality",
    "shadow-live",
)

FORBIDDEN_DOC_PHRASES = (
    "guaranteed profit",
    "risk-free",
    "production-ready",
    "autonomous live trading ready",
    "live trading enabled",
)

NEGATIVE_CONTEXT_INDICATORS = (
    "not ",
    "does not",
    "must not",
    "does **not**",
)

FORBIDDEN_MODULE_REFERENCES = (
    "atlas_agent.brokers",
    "atlas_agent.providers",
    "atlas_agent.execution.live",
    "atlas_agent.research.provider_",
    "get_research_provider",
)

FORBIDDEN_BROKER_PATTERNS = (
    "BrokerResolver(",
    ".resolve_execution_broker(",
    ".resolve_sync_provider(",
    ".resolve_status(",
    "guard_submit(",
    "guard_sync(",
)

FORBIDDEN_SUBMISSION_PATTERNS = (
    ".place_order(",
    ".cancel_order(",
    ".flatten_all(",
    "broker.submit",
    "OrderRouter(",
    ".route(",
    "run_submit_execution(",
    "mark_submit_*",
    "compute_client_order_id(",
)

FORBIDDEN_PROVIDER_CALL_PATTERNS = (
    "provider.execute",
    "provider.submit",
    "provider.complete(",
    "provider.generate(",
)

FORBIDDEN_CREDENTIAL_PATTERNS = (
    "load_atlas_secrets(",
    "get_secret(",
    "get_secret_status(",
    "set_secret(",
)

FORBIDDEN_LIVE_FLAG_PATTERNS = (
    "live_trading_enabled=True",
    "paper_only=False",
    "can_submit",
)

REQUIRED_QUALITY_STATES = (
    "not_evaluated",
    "blocked",
    "paper_activity_observed",
    "paper_quality_reviewable",
    "eligible_for_shadow_live_quality_review",
)

REQUIRED_DIMENSIONS = (
    "artifact_integrity",
    "stateful_resume_integrity",
    "trade_activity",
    "risk_rejection_coverage",
    "no_trade_coverage",
    "cost_accounting",
    "drawdown_bounds",
    "return_bounds",
    "exposure_bounds",
    "turnover_bounds",
    "benchmark_comparison",
    "replay_or_recompute_consistency",
    "data_coverage",
    "metric_validity",
    "no_live_side_effects",
)


def _sentence_around(text: str, index: int) -> str:
    start = text.rfind(".", 0, index) + 1
    end = text.find(".", index)
    if end == -1:
        end = len(text)
    return text[start:end].strip()


def _check_required_files() -> list[str]:
    return [f"Missing required file: {p.relative_to(REPO_ROOT)}" for p in REQUIRED_FILES if not p.is_file()]


def _check_required_doc_phrases() -> list[str]:
    if not DOC.is_file():
        return []
    text = DOC.read_text(encoding="utf-8").lower()
    return [f"Doc missing phrase: {phrase!r}" for phrase in REQUIRED_DOC_PHRASES if phrase.lower() not in text]


def _check_forbidden_doc_claims() -> list[str]:
    if not DOC.is_file():
        return []
    text = DOC.read_text(encoding="utf-8").lower()
    errors: list[str] = []
    for phrase in FORBIDDEN_DOC_PHRASES:
        index = text.find(phrase.lower())
        if index == -1:
            continue
        sentence = _sentence_around(text, index).lower()
        if not any(indicator in sentence for indicator in NEGATIVE_CONTEXT_INDICATORS):
            errors.append(f"Doc contains forbidden claim: {phrase!r} -> {sentence}")
    return errors


def _check_cross_references() -> list[str]:
    errors: list[str] = []
    for path in (DOC, GOVERNANCE_DOC):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8").lower()
        if "bounded-live-autonomy-governance.md" not in text and path != GOVERNANCE_DOC:
            errors.append(f"{path.name} missing cross-reference to bounded-live-autonomy-governance.md")
        if "shadow-live-readiness-contract.md" not in text:
            errors.append(f"{path.name} missing cross-reference to shadow-live-readiness-contract.md")
    return errors


def _check_cli_wiring() -> list[str]:
    if not CLI_MODULE.is_file():
        return ["CLI module not found."]
    text = CLI_MODULE.read_text(encoding="utf-8")
    if '"autonomous-paper-quality"' not in text:
        return ["CLI subparser 'autonomous-paper-quality' not wired in cli.py"]
    return []


def _check_module_safety() -> list[str]:
    errors: list[str] = []
    for module in MODULES:
        if not module.is_file():
            continue
        text = module.read_text(encoding="utf-8")
        for ref in FORBIDDEN_MODULE_REFERENCES:
            if ref in text:
                errors.append(f"{module.name}: forbidden reference {ref!r}")
        for pattern in FORBIDDEN_BROKER_PATTERNS + FORBIDDEN_SUBMISSION_PATTERNS + FORBIDDEN_PROVIDER_CALL_PATTERNS + FORBIDDEN_CREDENTIAL_PATTERNS + FORBIDDEN_LIVE_FLAG_PATTERNS:
            if pattern in text:
                errors.append(f"{module.name}: forbidden pattern {pattern!r}")
    return errors


def _check_quality_states_and_dimensions() -> list[str]:
    errors: list[str] = []
    module = MODULES[0]
    if not module.is_file():
        return [f"Module missing: {module.name}"]
    text = module.read_text(encoding="utf-8")
    for state in REQUIRED_QUALITY_STATES:
        if f'"{state}"' not in text:
            errors.append(f"Module missing quality state: {state!r}")
    for dimension in REQUIRED_DIMENSIONS:
        if f'"{dimension}"' not in text:
            errors.append(f"Module missing dimension: {dimension!r}")
    return errors


def check_all() -> dict[str, Any]:
    errors: list[str] = []
    errors.extend(_check_required_files())
    errors.extend(_check_required_doc_phrases())
    errors.extend(_check_forbidden_doc_claims())
    errors.extend(_check_cross_references())
    errors.extend(_check_cli_wiring())
    errors.extend(_check_module_safety())
    errors.extend(_check_quality_states_and_dimensions())
    return {"passed": not errors, "errors": errors}


def _redact(text: str) -> str:
    home = str(Path.home())
    repo = str(REPO_ROOT)
    return text.replace(home, "~").replace(repo, "<repo>")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check CAND-004 trading quality gate contract")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args()
    result = check_all()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result["passed"]:
            print("CAND-004 contract check: PASSED")
        else:
            print("CAND-004 contract check: FAILED")
            for error in result["errors"]:
                print(f"  - {_redact(error)}")
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
