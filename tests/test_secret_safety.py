from __future__ import annotations

import json

from omni_trade_ai.execution.audit import AuditLogger
from omni_trade_ai.safety.secrets import scan_text_for_secrets


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
