#!/usr/bin/env python3
"""Static check for the autonomous paper workflow demo and evidence gate (CAND-023).

Deterministic, local-only, read-only. Does not:
- call the network
- call GitHub API
- publish, upload, tag, or push
- require credentials
- execute live trading
- call brokers or providers
- mutate files

Exit codes:
  0 = pass
  1 = blocking findings
  2 = operational error
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from release_metadata import load_metadata, ReleaseMetadata
except ImportError:
    from scripts.release_metadata import load_metadata, ReleaseMetadata

_metadata_path = REPO_ROOT / "docs" / "releases" / "release-metadata.json"
_meta = ReleaseMetadata(load_metadata(_metadata_path))

PACKAGE_VERSION = _meta.source_version
CURRENT_PUBLIC_TAG = _meta.current_public_release
NEXT_PLANNED_TAG = _meta.next_planned_release

DEMO_DOC = REPO_ROOT / "docs" / "autonomous-paper-workflow.md"
DEMO_SCRIPT = REPO_ROOT / "scripts" / "demo_autonomous_paper_workflow.sh"
GOVERNANCE_DOC = REPO_ROOT / "docs" / "bounded-live-autonomy-governance.md"
ROADMAP_DOC = REPO_ROOT / "docs" / "autonomy-roadmap.md"
README = REPO_ROOT / "README.md"
PUBLIC_LAUNCH_READINESS = REPO_ROOT / "docs" / "public-launch-readiness.md"
TRUST_README = REPO_ROOT / "docs" / "trust" / "README.md"
REVIEWER_CHECKLIST = REPO_ROOT / "docs" / "reviewer-checklist.md"
RELEASE_METADATA_PATH = REPO_ROOT / "docs" / "releases" / "release-metadata.json"

REQUIRED_FILES = [
    DEMO_DOC,
    DEMO_SCRIPT,
    GOVERNANCE_DOC,
    ROADMAP_DOC,
]

REQUIRED_SCRIPT_COMMANDS = [
    "#!/usr/bin/env bash",
    "set -euo pipefail",
    "mktemp -d",
    "ATLAS-DEMO",
    "DEMO-SYMBOL",
    "discipline setup --manual --yes",
    "config set market.symbol",
    "validate",
    "run --mode paper --dry-run",
    "routine run",
    "--mode paper",
    "backtest run",
    "report generate",
    "audit verify --all",
]

FORBIDDEN_SCRIPT_PHRASES = [
    "rm -rf /",
    "enable_live_submit=true",
    "enable_live_trading=true",
    "TRADING_MODE=live",
    "--mode live",
    "twine" + " upload",
    "gh release create",
    "git tag ",
    "curl ",
    "wget ",
    "provider.execute",
    "execute_provider",
    "broker.submit",
    "broker.place_order",
    "submit_order",
    "set_secret",
]

REQUIRED_DOC_PHRASES = {
    DEMO_DOC: [
        "paper-only",
        "local-only",
        "no credentials",
        "Not financial advice",
        "does **not** claim autonomous-live-trading-readiness",
        "Bounded Live Autonomy Governance",
        "scripts/demo_autonomous_paper_workflow.sh",
        "scripts/check_autonomous_paper_workflow_demo.py",
        "ATLAS-DEMO",
        "DEMO-SYMBOL",
    ],
}

FORBIDDEN_DOC_PHRASES = [
    "autonomous live trading ready",
    "autonomous trading ready",
    "autonomous live trading is implemented",
    "autonomous live trading is supported",
    "unattended live trading",
    "safe live trading",
    "real-money autonomy ready",
    "production-ready for unattended",
    "unsupervised real-money trading is supported",
    "direct ai-to-broker execution is supported",
    "live trading ready",
    "production trading ready",
    "production-ready trading",
    "real-money ready",
    "real money ready",
    "safe to trade real money",
    "guaranteed profit",
    "profit guaranteed",
    "guaranteed returns",
    "verified alpha",
    "beats the market",
    "beat the market",
    "zero risk",
    "risk-free",
    "risk free",
    "no risk",
    "v0.6.13 is released",
    "released v0.6.13",
    "current public release v0.6.13",
    "tag v0.6.13 created",
    "github release v0.6.13 published",
    "v0.6.13 has been released",
    "pypi published",
    "publish to pypi",
    "published to pypi",
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
    "does **not**",
)

SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\bsk-proj-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\bAPCA-[A-Z0-9]{10,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{10,}", re.IGNORECASE),
]


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
    errors: list[str] = []
    for path in REQUIRED_FILES:
        if not path.exists():
            rel = path.relative_to(REPO_ROOT)
            errors.append(f"Required file missing: {rel}")
    return errors


def _check_demo_script() -> list[str]:
    errors: list[str] = []
    if not DEMO_SCRIPT.exists():
        errors.append("Demo script missing: scripts/demo_autonomous_paper_workflow.sh")
        return errors

    if not os.access(DEMO_SCRIPT, os.X_OK):
        errors.append("Demo script is not executable: scripts/demo_autonomous_paper_workflow.sh")

    text = _read(DEMO_SCRIPT)

    if not text.startswith("#!/usr/bin/env bash\nset -euo pipefail\n"):
        errors.append("Demo script missing safe shebang or set flags")

    for cmd in REQUIRED_SCRIPT_COMMANDS:
        if cmd not in text:
            errors.append(f"Demo script missing expected command/flag: {cmd}")

    for phrase in FORBIDDEN_SCRIPT_PHRASES:
        if phrase in text:
            errors.append(f"Demo script contains forbidden phrase: {phrase}")

    for pattern in SECRET_PATTERNS:
        for m in pattern.finditer(text):
            errors.append(
                f"Demo script contains secret-like pattern: {m.group(0)[:40]}"
            )

    return errors


def _check_required_doc_phrases() -> list[str]:
    errors: list[str] = []
    for path, phrases in REQUIRED_DOC_PHRASES.items():
        if not path.exists():
            continue
        text = _read(path)
        rel = path.relative_to(REPO_ROOT)
        for phrase in phrases:
            if phrase.lower() not in text.lower():
                errors.append(f"[{rel}] Missing required phrase: {phrase}")
    return errors


def _check_forbidden_doc_claims() -> list[str]:
    errors: list[str] = []
    for path in [DEMO_DOC, GOVERNANCE_DOC, ROADMAP_DOC]:
        if not path.exists():
            continue
        text = _read(path).lower()
        rel = path.relative_to(REPO_ROOT)
        for phrase in FORBIDDEN_DOC_PHRASES:
            start = text.find(phrase)
            while start != -1:
                end = start + len(phrase)
                sentence = _sentence_around(text, start, end).lower()
                if not any(ind in sentence for ind in NEGATIVE_CONTEXT_INDICATORS):
                    errors.append(
                        f"[{rel}] Forbidden phrase '{phrase}' outside negative context"
                    )
                start = text.find(phrase, end)
    return errors


def _check_cross_references() -> list[str]:
    errors: list[str] = []
    if DEMO_DOC.exists():
        text = _read(DEMO_DOC)
        for link in [
            "bounded-live-autonomy-governance.md",
            "autonomy-roadmap.md",
            "paper-trading-guide.md",
        ]:
            if link not in text:
                errors.append(f"[{DEMO_DOC.relative_to(REPO_ROOT)}] Missing link to {link}")

    for path, label in [
        (README, "README.md"),
        (GOVERNANCE_DOC, "docs/bounded-live-autonomy-governance.md"),
        (ROADMAP_DOC, "docs/autonomy-roadmap.md"),
        (PUBLIC_LAUNCH_READINESS, "docs/public-launch-readiness.md"),
        (TRUST_README, "docs/trust/README.md"),
        (REVIEWER_CHECKLIST, "docs/reviewer-checklist.md"),
    ]:
        if not path.exists():
            continue
        text = _read(path)
        if "autonomous-paper-workflow.md" not in text:
            errors.append(f"[{label}] Missing link to autonomous-paper-workflow.md")

    return errors


def _check_release_metadata() -> list[str]:
    errors: list[str] = []
    if PACKAGE_VERSION != "0.6.22":
        errors.append(
            f"Source version {PACKAGE_VERSION} != 0.6.22"
        )
    if CURRENT_PUBLIC_TAG != "v0.6.22":
        errors.append(f"Current public release {CURRENT_PUBLIC_TAG} != v0.6.22")
    if NEXT_PLANNED_TAG not in ("v0.6.23", "0.6.23"):
        errors.append(f"Next planned release {NEXT_PLANNED_TAG} != v0.6.23")

    result = subprocess.run(
        ["git", "tag", "--list", NEXT_PLANNED_TAG],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        errors.append(f"Local git tag {NEXT_PLANNED_TAG} already exists")

    return errors


def _run_checks() -> dict:
    errors: list[str] = []

    errors.extend(_check_required_files())
    errors.extend(_check_demo_script())
    errors.extend(_check_required_doc_phrases())
    errors.extend(_check_forbidden_doc_claims())
    errors.extend(_check_cross_references())
    errors.extend(_check_release_metadata())

    return {
        "passed": len(errors) == 0,
        "package_version": PACKAGE_VERSION,
        "current_public_tag": CURRENT_PUBLIC_TAG,
        "next_planned_tag": NEXT_PLANNED_TAG,
        "errors": errors,
    }


def _redact(text: str) -> str:
    home = str(Path.home())
    repo = str(REPO_ROOT)
    replacements = [
        (home, "~"),
        (repo, "<repo>"),
        ("/Users/", "<home>/"),
        ("/private/var/", "<temp>/"),
        ("/var/folders/", "<temp>/"),
        ("/tmp/", "<temp>/"),
        ("/var/tmp/", "<temp>/"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Autonomous paper workflow demo and evidence gate check."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON.",
    )
    args = parser.parse_args()

    try:
        result = _run_checks()
    except Exception as exc:
        if args.json:
            print(json.dumps({"error": str(exc), "passed": False}))
        else:
            print(f"Operational error: {exc}")
        return 2

    if args.json:
        output = {
            "passed": result["passed"],
            "package_version": result["package_version"],
            "current_public_tag": result["current_public_tag"],
            "next_planned_tag": result["next_planned_tag"],
            "errors": [_redact(e) for e in result["errors"]],
        }
        print(json.dumps(output, indent=2))
        return 0 if result["passed"] else 1

    if result["errors"]:
        print("Autonomous paper workflow demo check FAILED")
        for e in result["errors"]:
            print(f"  - {_redact(e)}")
        return 1

    print("Autonomous paper workflow demo check PASSED")
    print(f"  Package version: {result['package_version']}")
    print(f"  Current public tag: {result['current_public_tag']}")
    print(f"  Next planned tag: {result['next_planned_tag']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
