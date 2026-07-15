# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_docs_v040.py
# PURPOSE: Verifies docs v040 behavior and regression expectations.
# DEPS:    re, pytest, pathlib, tomllib.
# ==============================================================================

# --- IMPORTS ---

import re
from functools import lru_cache

import pytest
from pathlib import Path
import tomllib


# --- CONFIGURATION AND CONSTANTS ---

_RUNTIME_MARKDOWN_DIRS = {"artifacts", "memory", "reports"}


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def get_markdown_files():
    return [
        path
        for path in Path(".").glob("**/*.md")
        if _RUNTIME_MARKDOWN_DIRS.isdisjoint(path.parts)
    ]

# CAND-012 docs document forbidden phrases as labeled examples in a table.
# They are covered by the repository-level forbidden-claims checker and must not
# be treated as making the claims themselves.
_FORBIDDEN_EXAMPLE_DOCS = {
    "docs/candidate-chain-consistency-guard-design.md",
    "docs/candidate-chain-consistency-guard-implementation-plan.md",
}


@pytest.fixture(scope="module")
def markdown_documents() -> dict[Path, str]:
    """Read each stable markdown document once for all repository-wide scans."""
    return {
        path: path.read_text(encoding="utf-8")
        for path in get_markdown_files()
        if path.exists()
    }


def test_no_forbidden_terms(markdown_documents: dict[Path, str]) -> None:
    forbidden = (
        "hermes",
        "tamper-proof",
        "encrypted workspace",
        "atlas brokers sync",
        "backtest --strategy",
        "risk-free",
        "guaranteed profit",
        "predicts profit",
        "self-improving ai trading agent",
        "professional-grade toolset",
        "production-grade live",
        "makes money",
        "best broker",
        "recommended broker",
        "magic ai trading bot",
        "autonomous profit system",
    )
    violations = []

    for file_path, content in markdown_documents.items():
        if str(file_path) in _FORBIDDEN_EXAMPLE_DOCS:
            continue
        lower_content = content.lower()
        violations.extend(
            f"Forbidden term '{term}' found in {file_path}"
            for term in forbidden
            if term in lower_content
        )

    # Aggregate failures to retain per-file diagnostics without one pytest item
    # per document, which previously duplicated collection and scheduling work.
    assert violations == [], "\n".join(violations)

def _project_version() -> str:
    with Path("pyproject.toml").open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def _public_version_label(version: str) -> str:
    """Map PEP 440 package version to public display/tag version.

    Examples:
        0.5.7rc1 -> v0.5.7-rc1
        0.5.7.dev50 -> v0.5.7.dev50
        0.5.7 -> v0.5.7
    """
    m = re.fullmatch(r"(\d+\.\d+\.\d+)rc(\d+)", version)
    if m:
        return f"v{m.group(1)}-rc{m.group(2)}"
    return f"v{version}"


def test_readme_contains_v030_essentials(release_identity: dict):
    readme = Path("README.md").read_text(encoding="utf-8")

    # The README shows the latest public release tag as current status,
    # which may differ from the source package version during release prep.
    essentials = [
        f"Current Status ({release_identity['current_public_release']})",
        "atlas backtest run",
        "atlas broker sync",
        "read-only",
        "tamper-evident",
        "hash-chain",
        "kill switch",
        "heartbeat",
        "live submit remains disabled by default"
    ]

    for item in essentials:
        assert item.lower() in readme.lower(), f"Essential term '{item}' missing from README.md"

def test_no_stale_v02_references(markdown_documents: dict[Path, str]):
    for file_path, content in markdown_documents.items():
        assert "Current Status (v0.2" not in content, f"Stale status reference found in {file_path}"

def test_no_stale_v054_references(markdown_documents: dict[Path, str]):
    # Skip historical/audit files that intentionally reference past versions
    skip_patterns = ("changelog", "audit_enhancements", "history", "release-notes")
    for file_path, content in markdown_documents.items():
        path_lower = str(file_path).lower()
        if any(skip in path_lower for skip in skip_patterns):
            continue
        assert "v0.5.4" not in content, f"Stale v0.5.4 reference found in {file_path}"


def test_no_forbidden_live_maturity_terms(markdown_documents: dict[Path, str]):
    extra_forbidden = [
        "fully supported live broker",
        "autonomous trading bot",
        "production-grade live trading",
    ]
    for file_path, document in markdown_documents.items():
        content = document.lower()
        for term in extra_forbidden:
            assert term not in content, f"Forbidden maturity term '{term}' found in {file_path}"


def test_env_var_docs_use_canonical_alpaca_names():
    env_doc = Path("docs/environment-variables.md").read_text(encoding="utf-8")
    assert "ALPACA_API_KEY=" in env_doc, "docs/environment-variables.md must use ALPACA_API_KEY"
    assert "ALPACA_SECRET_KEY=" in env_doc, "docs/environment-variables.md must use ALPACA_SECRET_KEY"
    assert "APCA_API_KEY_ID=" not in env_doc, "docs/environment-variables.md must not use stale APCA_API_KEY_ID"
    assert "APCA_API_SECRET_KEY=" not in env_doc, "docs/environment-variables.md must not use stale APCA_API_SECRET_KEY"


def test_env_var_docs_use_canonical_binance_secret():
    env_doc = Path("docs/environment-variables.md").read_text(encoding="utf-8")
    assert "BINANCE_API_SECRET=" in env_doc, "docs/environment-variables.md must list BINANCE_API_SECRET"
    assert "BINANCE_SECRET_KEY=" in env_doc, "docs/environment-variables.md must mention BINANCE_SECRET_KEY as legacy alias"


def test_live_alpaca_demo_uses_canonical_env_names():
    demo_doc = Path("examples/live_alpaca_demo/README.md").read_text(encoding="utf-8")
    assert "ALPACA_API_KEY=" in demo_doc, "live_alpaca_demo must use ALPACA_API_KEY"
    assert "ALPACA_SECRET_KEY=" in demo_doc, "live_alpaca_demo must use ALPACA_SECRET_KEY"
    assert "APCA_API_KEY_ID=" not in demo_doc, "live_alpaca_demo must not use stale APCA_API_KEY_ID"
    assert "APCA_API_SECRET_KEY=" not in demo_doc, "live_alpaca_demo must not use stale APCA_API_SECRET_KEY"


def test_no_realistic_keys_in_docs(markdown_documents: dict[Path, str]):
    # Very simple check for common key patterns
    key_patterns = ["sk-", "AKIA"]
    for file_path, content in markdown_documents.items():
        for pattern in key_patterns:
            # We allow patterns like YOUR_ALPACA_KEY
            # But not realistic looking ones
            import re
            # Match sk- followed by ~20+ alphanumeric chars
            if re.search(pattern + r"[a-zA-Z0-9]{20,}", content):
                 pytest.fail(f"Realistic looking API key pattern found in {file_path}")


# ---------------------------------------------------------------------------
# Broker Foundation 3.4 docs-truth tests
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _docs_text() -> str:
    """Combined text of all docs/ markdown files."""
    texts = []
    for p in Path("docs").glob("*.md"):
        texts.append(p.read_text(encoding="utf-8"))
    return "\n".join(texts).lower()


def test_docs_do_not_claim_alpaca_sync_is_stubbed():
    text = _docs_text()
    # Alpaca sync is now implemented; docs must not claim it is stubbed
    bad_phrases = [
        "alpaca ... sync are stubbed",
        "alpaca ... account and position sync are stubbed",
        "live adapters currently have stubbed account and position sync",
    ]
    for phrase in bad_phrases:
        assert phrase not in text, f"Docs still claim Alpaca sync is stubbed: {phrase}"


def test_docs_do_not_claim_live_sync_globally_deferred():
    text = _docs_text()
    # Live Alpaca sync exists; broad "live sync deferred" is stale
    bad_phrases = [
        "live sync is currently deferred",
        "live sync depends on adapter maturity and is deferred",
        "live sync depends on adapter maturity: paperbrokeradapter supports full sync, while live adapters currently have stubbed",
        "active broker synchronization (deferred until live adapter maturity)",
    ]
    for phrase in bad_phrases:
        assert phrase not in text, f"Docs still claim live sync is globally deferred: {phrase}"


def test_docs_mention_live_analysis_only():
    text = _docs_text()
    assert "live_analysis_only" in text, "Docs must mention live_analysis_only"


def test_docs_mention_can_submit_false_or_submit_disabled():
    text = _docs_text()
    assert (
        "can_submit=false" in text
        or "can_submit = false" in text
        or "submit remains disabled" in text
        or "live submit remains gated and disabled" in text
    ), "Docs must mention that live can_submit is false or submit is disabled"


def test_docs_mention_resolve_execution_broker_live_returns_none():
    text = _docs_text()
    assert (
        "resolve_execution_broker(\"live\")" in text
        or "resolve_execution_broker('live')" in text
        or "returns none" in text
    ), "Docs must mention resolve_execution_broker('live') behavior or equivalent"


def test_docs_mention_binance_ccxt_ibkr_deferred():
    text = _docs_text()
    assert "binance" in text and "deferred" in text, "Docs must mention Binance/CCXT/IBKR deferred status"


def test_docs_do_not_claim_live_agent_creates_pending_orders():
    text = _docs_text()
    bad_phrases = [
        "in live mode, proposed orders are first written to disk as pending approval records",
        "live mode ... pending_orders",
    ]
    for phrase in bad_phrases:
        assert phrase not in text, f"Docs incorrectly claim live agent creates pending orders: {phrase}"


def test_docs_mention_alpaca_read_only_sync():
    text = _docs_text()
    assert "alpaca read-only" in text or "alpaca read only" in text, "Docs must mention Alpaca read-only sync"
