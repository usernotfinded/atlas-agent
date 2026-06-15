#!/usr/bin/env python3
"""Validate the v0.6.12 Product Demo and Marketplace Readiness Pack.

Checks that demo scripts, artifact indexes, public-facing docs, and marketplace
readiness materials are present, internally consistent, and free of unsafe or
over-promising claims. Local-only and read-only: does not publish, tag, push,
load credentials, access the network, submit broker orders, call providers,
enable live trading, or execute the demo workflows.

Exit codes:
  0 = valid
  1 = blocking findings
  2 = operational error
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_FILES = [
    REPO_ROOT / "docs" / "product-demo-pack.md",
    REPO_ROOT / "docs" / "marketplace-listing.md",
    REPO_ROOT / "docs" / "autonomy-roadmap.md",
    REPO_ROOT / "scripts" / "demo_product_walkthrough.sh",
    REPO_ROOT / "scripts" / "check_product_demo_pack.py",
    REPO_ROOT / "tests" / "test_product_demo_pack.py",
]

DEMO_SCRIPT = REPO_ROOT / "scripts" / "demo_product_walkthrough.sh"
PRODUCT_DEMO_DOC = REPO_ROOT / "docs" / "product-demo-pack.md"
MARKETPLACE_DOC = REPO_ROOT / "docs" / "marketplace-listing.md"
AUTONOMY_DOC = REPO_ROOT / "docs" / "autonomy-roadmap.md"
README = REPO_ROOT / "README.md"
PAPER_WORKFLOW_DOC = REPO_ROOT / "docs" / "demo-paper-workflow.md"

REQUIRED_DOC_PHRASES = {
    PRODUCT_DEMO_DOC: [
        "Not financial advice",
        "paper-only",
        "offline",
        "no credentials",
        "no live trading",
        "scripts/demo_paper_workflow.sh",
        "scripts/demo_product_walkthrough.sh",
        "data/sample/ohlcv.csv",
        "DEMO-SYMBOL",
        "ATLAS-DEMO",
    ],
    MARKETPLACE_DOC: [
        "Not financial advice",
        "Live trading is disabled by default",
        "paper-first",
        "broker-neutral",
        "no credentials",
        "safe-by-default",
        "not autonomous",
        "not a live-trading-ready product",
    ],
    AUTONOMY_DOC: [
        "Not financial advice",
        "supervised, not autonomous",
        "No promise of profitability",
        "L0",
        "L1",
        "L2",
        "L3",
        "L4",
        "not a project goal",
        "not implemented in the current release",
        "out of scope",
    ],
}

FORBIDDEN_MARKETPLACE_PHRASES = [
    "live trading ready",
    "production trading ready",
    "production-ready trading",
    "real-money ready",
    "real money ready",
    "autonomous trading ready",
    "fully autonomous",
    "safe live trading",
    "safe to trade real money",
    "guaranteed profit",
    "guaranteed returns",
    "profitable strategy",
    "verified alpha",
    "beats the market",
    "beat the market",
    "makes money",
    "earns money",
    "passive income",
    "financial freedom",
    "zero risk",
    "risk-free",
    "risk free",
    "no risk",
    "use atlas with real money",
    "connect real broker credentials",
    "trade real money",
    "start live trading now",
    "enable live trading",
    "link your broker account",
    "provider execution enabled",
    "unlock provider execution",
    "unlock the provider",
    "broker order submission enabled",
    "enable broker submission",
    "can_submit=true",
    "auto_within_limits",
    "set and forget",
    "unattended live trading",
]

FORBIDDEN_SCRIPT_PHRASES = [
    "rm -rf /",
    "set_secret",
    "enable_live_trading = true",
    "enable_live_submit = true",
    "can_submit=true",
    "--mode live",
    "curl ",
    "wget ",
    "provider.execute",
    "execute_provider",
    "broker.submit",
    "submit_order",
]

REQUIRED_SCRIPT_COMMANDS = [
    "mktemp -d",
    "ATLAS-DEMO",
    "DEMO-SYMBOL",
    "discipline setup --manual --yes",
    "config set market.symbol",
    "validate",
    "doctor --json",
    "run --mode paper --dry-run",
    "backtest run",
    "audit verify --all",
]

SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\bsk-proj-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\bAPCA-[A-Z0-9]{10,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{10,}", re.IGNORECASE),
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
    "out of scope",
)


def _read(path: Path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _sentence_around(text: str, start: int, end: int) -> str:
    boundary_chars = {".", "!", "?", "\n"}
    s = start
    while s > 0 and text[s - 1] not in boundary_chars:
        s -= 1
    e = end
    while e < len(text) and text[e] not in boundary_chars:
        e += 1
    return text[s:e]


def _check_required_files() -> list[str]:
    violations: list[str] = []
    for path in REQUIRED_FILES:
        if not path.exists():
            rel = path.relative_to(REPO_ROOT)
            violations.append(f"Required file missing: {rel}")
    return violations


def _check_demo_script_executable() -> list[str]:
    violations: list[str] = []
    if not DEMO_SCRIPT.exists():
        violations.append("Demo script missing: scripts/demo_product_walkthrough.sh")
        return violations
    if not os.access(DEMO_SCRIPT, os.X_OK):
        violations.append("Demo script is not executable: scripts/demo_product_walkthrough.sh")
    return violations


def _check_demo_script_shebang_and_flags(text: str) -> list[str]:
    violations: list[str] = []
    if not text.startswith("#!/usr/bin/env bash\nset -euo pipefail\n"):
        violations.append("Demo script missing safe shebang or set flags")
    return violations


def _check_demo_script_required_commands(text: str) -> list[str]:
    violations: list[str] = []
    for cmd in REQUIRED_SCRIPT_COMMANDS:
        if cmd not in text:
            violations.append(f"Demo script missing expected command: {cmd}")
    return violations


def _check_demo_script_forbidden_phrases(text: str) -> list[str]:
    violations: list[str] = []
    for phrase in FORBIDDEN_SCRIPT_PHRASES:
        if phrase in text:
            violations.append(f"Demo script contains forbidden phrase: {phrase}")
    return violations


def _check_required_doc_phrases() -> list[str]:
    violations: list[str] = []
    for path, phrases in REQUIRED_DOC_PHRASES.items():
        if not path.exists():
            continue
        text = _read(path)
        rel = path.relative_to(REPO_ROOT)
        for phrase in phrases:
            if phrase.lower() not in text.lower():
                violations.append(f"[{rel}] Missing required phrase: {phrase}")
    return violations


def _check_forbidden_claims_in_docs() -> list[str]:
    violations: list[str] = []
    for path in [PRODUCT_DEMO_DOC, MARKETPLACE_DOC, AUTONOMY_DOC]:
        if not path.exists():
            continue
        text = _read(path).lower()
        rel = path.relative_to(REPO_ROOT)
        for phrase in FORBIDDEN_MARKETPLACE_PHRASES:
            start = text.find(phrase)
            while start != -1:
                end = start + len(phrase)
                sentence = _sentence_around(text, start, end).lower()
                if not any(ind in sentence for ind in NEGATIVE_CONTEXT_INDICATORS):
                    violations.append(
                        f"[{rel}] Forbidden phrase '{phrase}' outside negative context"
                    )
                start = text.find(phrase, end)
    return violations


def _check_marketplace_implications() -> list[str]:
    violations: list[str] = []
    if not MARKETPLACE_DOC.exists():
        return violations
    text = _read(MARKETPLACE_DOC).lower()
    required_phrases = [
        "not financial advice",
        "live trading is disabled by default",
        "paper trading",
        "sandbox",
    ]
    for phrase in required_phrases:
        if phrase not in text:
            violations.append(
                f"[docs/marketplace-listing.md] Missing required marketplace safety phrase: {phrase}"
            )
    required_headings = [
        "## tagline",
        "## one-paragraph product description",
        "## target users",
        "## current capabilities",
        "## what is disabled",
        "## safety boundaries",
        "## getting started",
        "## disclaimer",
    ]
    lower_text = text
    for heading in required_headings:
        if heading not in lower_text:
            violations.append(
                f"[docs/marketplace-listing.md] Missing required section: {heading.lstrip('# ')}"
            )
    return violations


def _check_autonomy_roadmap_clarity() -> list[str]:
    violations: list[str] = []
    if not AUTONOMY_DOC.exists():
        return violations
    text = _read(AUTONOMY_DOC).lower()
    current_markers = [
        "current state",
        "not implemented in the current release",
        "out of scope",
        "not a project goal",
    ]
    if not any(marker in text for marker in current_markers):
        violations.append(
            "[docs/autonomy-roadmap.md] Missing current/future-state marker for autonomy levels"
        )
    if "not autonomous" not in text:
        violations.append(
            "[docs/autonomy-roadmap.md] Missing explicit 'not autonomous' framing"
        )
    return violations


def _check_cross_references() -> list[str]:
    violations: list[str] = []
    if not PRODUCT_DEMO_DOC.exists():
        return violations
    text = _read(PRODUCT_DEMO_DOC)
    for link in [
        "marketplace-listing.md",
        "autonomy-roadmap.md",
        "demo_product_walkthrough.sh",
        "check_product_demo_pack.py",
    ]:
        if link not in text:
            violations.append(f"[docs/product-demo-pack.md] Missing link to {link}")
    return violations


def _check_readme_links_to_pack() -> list[str]:
    violations: list[str] = []
    if not README.exists():
        return violations
    text = _read(README)
    for link in [
        "docs/product-demo-pack.md",
        "scripts/demo_product_walkthrough.sh",
    ]:
        if link not in text:
            violations.append(f"[README.md] Missing link to {link}")
    return violations


def _check_secrets_in_demo_surfaces() -> list[str]:
    violations: list[str] = []
    for path in [DEMO_SCRIPT, PRODUCT_DEMO_DOC, MARKETPLACE_DOC, AUTONOMY_DOC]:
        if not path.exists():
            continue
        text = _read(path)
        rel = path.relative_to(REPO_ROOT)
        for pattern in SECRET_PATTERNS:
            for m in pattern.finditer(text):
                violations.append(
                    f"[{rel}] Secret-like pattern matched: {m.group(0)[:40]}"
                )
    return violations


def _check_absolute_paths_in_docs() -> list[str]:
    violations: list[str] = []
    for path in [PRODUCT_DEMO_DOC, MARKETPLACE_DOC, AUTONOMY_DOC]:
        if not path.exists():
            continue
        text = _read(path)
        rel = path.relative_to(REPO_ROOT)
        for prefix in ["/Users/", "/private/var/", "/var/folders/"]:
            if prefix in text:
                violations.append(f"[{rel}] Absolute path fragment found: {prefix}")
    return violations


def run_checks() -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    errors.extend(_check_required_files())
    errors.extend(_check_demo_script_executable())

    if DEMO_SCRIPT.exists():
        script_text = _read(DEMO_SCRIPT)
        errors.extend(_check_demo_script_shebang_and_flags(script_text))
        errors.extend(_check_demo_script_required_commands(script_text))
        errors.extend(_check_demo_script_forbidden_phrases(script_text))

    errors.extend(_check_required_doc_phrases())
    errors.extend(_check_forbidden_claims_in_docs())
    errors.extend(_check_marketplace_implications())
    errors.extend(_check_autonomy_roadmap_clarity())
    errors.extend(_check_cross_references())
    errors.extend(_check_readme_links_to_pack())
    errors.extend(_check_secrets_in_demo_surfaces())
    errors.extend(_check_absolute_paths_in_docs())

    if not PAPER_WORKFLOW_DOC.exists():
        warnings.append("docs/demo-paper-workflow.md not found; canonical demo doc missing")

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "files_checked": len(REQUIRED_FILES) + 1,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check product demo and marketplace readiness materials. "
        "Static, local-only, and read-only."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output.",
    )
    args = parser.parse_args(argv)

    result = run_checks()

    if args.json:
        import json

        summary = (
            "Product demo and marketplace readiness check PASSED"
            if result["passed"]
            else "Product demo and marketplace readiness check FAILED"
        )
        print(
            json.dumps(
                {
                    "passed": result["passed"],
                    "files_checked": result["files_checked"],
                    "summary": summary,
                    "errors": result["errors"],
                    "warnings": result["warnings"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if result["passed"] else 1

    if result["errors"]:
        print("Product demo and marketplace readiness check FAILED")
        for error in result["errors"]:
            print(f"  - {error}")
    else:
        print("Product demo and marketplace readiness check PASSED")
        print(f"  Files checked: {result['files_checked']}")

    if result["warnings"]:
        for warning in result["warnings"]:
            print(f"  WARN: {warning}")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
