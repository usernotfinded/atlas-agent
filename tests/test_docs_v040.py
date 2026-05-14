import pytest
from pathlib import Path
import tomllib

def get_markdown_files():
    return list(Path(".").glob("**/*.md"))

@pytest.mark.parametrize("file_path", get_markdown_files())
def test_no_forbidden_terms(file_path):
    # Skip reports and memory files which might contain legacy data or logs
    if "reports/" in str(file_path) or "memory/" in str(file_path):
        return
        
    content = file_path.read_text(encoding="utf-8").lower()
    
    forbidden = [
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
        "autonomous profit system"
    ]
    
    for term in forbidden:
        assert term not in content, f"Forbidden term '{term}' found in {file_path}"

def _project_version() -> str:
    with Path("pyproject.toml").open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def test_readme_contains_v030_essentials():
    readme = Path("README.md").read_text(encoding="utf-8")
    
    essentials = [
        f"Current Status (v{_project_version()})",
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

def test_no_stale_v02_references():
    for file_path in get_markdown_files():
        if "reports/" in str(file_path) or "memory/" in str(file_path):
            continue
        content = file_path.read_text(encoding="utf-8")
        assert "Current Status (v0.2" not in content, f"Stale status reference found in {file_path}"

def test_no_stale_v054_references():
    # Skip historical/audit files that intentionally reference past versions
    skip_patterns = ("changelog", "audit_enhancements", "history", "release-notes")
    for file_path in get_markdown_files():
        path_lower = str(file_path).lower()
        if "reports/" in path_lower or "memory/" in path_lower:
            continue
        if any(skip in path_lower for skip in skip_patterns):
            continue
        content = file_path.read_text(encoding="utf-8")
        assert "v0.5.4" not in content, f"Stale v0.5.4 reference found in {file_path}"


def test_no_forbidden_live_maturity_terms():
    extra_forbidden = [
        "fully supported live broker",
        "autonomous trading bot",
        "production-grade live trading",
    ]
    for file_path in get_markdown_files():
        if "reports/" in str(file_path) or "memory/" in str(file_path):
            continue
        content = file_path.read_text(encoding="utf-8").lower()
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


def test_no_realistic_keys_in_docs():
    # Very simple check for common key patterns
    key_patterns = ["sk-", "AKIA"]
    for file_path in get_markdown_files():
        if "reports/" in str(file_path) or "memory/" in str(file_path):
            continue
        content = file_path.read_text(encoding="utf-8")
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
