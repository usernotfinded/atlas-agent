# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/audit/test_audit_redaction.py
# PURPOSE: Verifies audit redaction behavior and regression expectations.
# DEPS:    atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

from atlas_agent.audit.redaction import redact_payload, refresh_redaction_secrets


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_redaction_removes_secrets_recursively():
    payload = {
        "api_key": "sk-12345",
        "nested": {
            "token": "secret-token",
            "safe": "data"
        },
        "list": [
            {"password": "pass"},
            "safe"
        ]
    }
    
    redacted = redact_payload(payload)
    
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["nested"]["token"] == "[REDACTED]"
    assert redacted["nested"]["safe"] == "data"
    assert redacted["list"][0]["password"] == "[REDACTED]"
    assert redacted["list"][1] == "safe"


def test_redaction_is_case_insensitive():
    payload = {"Authorization": "Bearer key"}
    assert redact_payload(payload)["Authorization"] == "[REDACTED]"


def test_redaction_handles_various_markers():
    markers = ["API_KEY", "TOKEN", "SECRET", "PASSWORD", "AUTH", "COOKIE"]
    for marker in markers:
        payload = {marker: "val"}
        assert redact_payload(payload)[marker] == "[REDACTED]"

def test_redact_payload_free_text_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "super_secret_openai_key")
    refresh_redaction_secrets()
    
    payload = "Here is a prompt containing super_secret_openai_key inside it."
    redacted = redact_payload(payload)
    assert redacted == "Here is a prompt containing [REDACTED] inside it."
    
    dict_payload = {
        "message": "My key is super_secret_openai_key!"
    }
    redacted_dict = redact_payload(dict_payload)
    assert redacted_dict["message"] == "My key is [REDACTED]!"


def test_audit_events_redact_secrets_before_hashing(tmp_path, monkeypatch):
    """Written events must carry no secret, in any placement the engine covers."""
    import json

    from atlas_agent.audit.writer import AuditWriter
    from atlas_agent.redaction import refresh_redaction_secrets

    secret = "sk-live-AUDITPROBE123456"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    refresh_redaction_secrets()

    log_path = tmp_path / "events.jsonl"
    writer = AuditWriter(audit_path=log_path)
    writer.start_run("run-1")
    writer.write_event(
        "provider_called",
        run_id="run-1",
        iteration=0,
        payload={
            "api_key": secret,
            "prose": f"calling with {secret}",
            "headers": {"Authorization": f"Bearer {secret}"},
            "nested": [{"token": secret}],
            "env_line": f"OPENAI_API_KEY={secret}",
        },
    )

    raw = log_path.read_text(encoding="utf-8")
    assert secret not in raw

    payload = json.loads(raw.splitlines()[-1])["payload"]
    assert payload["api_key"] == "[REDACTED]"
    assert "[REDACTED]" in payload["prose"]
    assert "[REDACTED]" in payload["headers"]["Authorization"]
    assert payload["nested"][0]["token"] == "[REDACTED]"


def test_redaction_covers_an_unannounced_credential_by_shape(tmp_path):
    """Pattern rules catch a secret the engine was never told about."""
    import json

    from atlas_agent.audit.writer import AuditWriter

    never_registered = "sk-late-NOTINTHESNAPSHOT987654"

    log_path = tmp_path / "events.jsonl"
    writer = AuditWriter(audit_path=log_path)
    writer.start_run("run-1")
    writer.write_event(
        "provider_called",
        run_id="run-1",
        iteration=0,
        payload={
            "api_key": never_registered,
            "headers": {"Authorization": f"Bearer {never_registered}"},
            "env_line": f"SOME_LATE_KEY={never_registered}",
        },
    )

    assert never_registered not in log_path.read_text(encoding="utf-8")


def test_redaction_cannot_reach_an_opaque_value_under_an_innocuous_key(tmp_path):
    """The boundary: redaction is value- and pattern-based, not clairvoyant.

    A credential with no recognisable shape, under a key that does not read as
    sensitive, is invisible to the scrubber unless it was announced through
    `refresh_redaction_secrets`. This is pinned so the limit stays a known
    property rather than a surprise, and so callers keep treating "do not put
    credentials in a payload" as the actual rule.
    """
    import json

    from atlas_agent.audit.writer import AuditWriter

    opaque = "Xq7Tp2Rv9Lm4Kd8Nb3Wz"

    log_path = tmp_path / "events.jsonl"
    writer = AuditWriter(audit_path=log_path)
    writer.start_run("run-1")
    writer.write_event(
        "tool_call_requested",
        run_id="run-1",
        iteration=0,
        payload={"comment": f"the operator pasted {opaque} into the console"},
    )

    assert opaque in log_path.read_text(encoding="utf-8")
