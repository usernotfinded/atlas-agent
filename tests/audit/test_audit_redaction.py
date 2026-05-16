from __future__ import annotations

from atlas_agent.audit.redaction import redact_payload, refresh_redaction_secrets


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
