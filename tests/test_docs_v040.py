import pytest
from pathlib import Path

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

def test_readme_contains_v030_essentials():
    readme = Path("README.md").read_text(encoding="utf-8")
    
    essentials = [
        "Current Status (v0.5.2)",
        "atlas backtest run",
        "atlas broker sync",
        "read-only",
        "tamper-evident",
        "hash-chain",
        "kill switch",
        "heartbeat",
        "live trading | disabled by default"
    ]
    
    for item in essentials:
        assert item.lower() in readme.lower(), f"Essential term '{item}' missing from README.md"

def test_no_stale_v02_references():
    for file_path in get_markdown_files():
        if "reports/" in str(file_path) or "memory/" in str(file_path):
            continue
        content = file_path.read_text(encoding="utf-8")
        assert "Current Status (v0.2" not in content, f"Stale status reference found in {file_path}"

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
