from __future__ import annotations

import json

from atlas_agent.execution.audit import AuditLogger
from atlas_agent.safety.secrets import scan_text_for_secrets


def test_no_broker_logs_secrets(tmp_path) -> None:
    logger = AuditLogger(tmp_path)
    logger.write("test", {"ALPACA_API_KEY": "secret", "safe": "value"})

    record = json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8"))

    assert record["payload"]["ALPACA_API_KEY"] == "[REDACTED]"
    assert "secret" not in (tmp_path / "audit.jsonl").read_text(encoding="utf-8")


def test_secret_scanner_detects_real_values() -> None:
    generic_key = "API_KEY="
    alpaca_key = "ALPACA_API_KEY="
    token_key = "TOKEN="
    findings = scan_text_for_secrets(
        generic_key + "abc\n" + alpaca_key + "secret\n" + token_key + "\n"
    )

    assert findings == ["API_KEY", "ALPACA_API_KEY"]


def test_public_docs_do_not_add_profit_claims() -> None:
    checked = [
        "README.md",
        "DISCLAIMER.md",
        "docs/model-roster.md",
    ]
    text = "\n".join(open(path, encoding="utf-8").read() for path in checked).lower()

    assert "guaranteed profit" not in text
    assert "profit guarantee" in text or "no returns are guaranteed" in text
