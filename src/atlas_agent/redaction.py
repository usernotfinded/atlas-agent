from __future__ import annotations

import os
import re
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from atlas_agent.config.secrets import is_secret_key


REDACTED_VALUE = "[REDACTED]"

SECRET_MARKERS = (
    "KEY",
    "API_KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "AUTHORIZATION",
    "AUTH",
    "BEARER",
    "COOKIE",
    "PRIVATE_KEY",
)
SECRET_FIELD_NAMES = {
    "API_KEY",
    "SECRET",
    "TOKEN",
    "AUTH",
    "PASSWORD",
    "ALPACA_SECRET_KEY",
    "OPENAI_COMPATIBLE_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "KIMI_API_KEY",
    "GROK_API_KEY",
    "OPENROUTER_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "CLICKUP_API_TOKEN",
}
SAFE_ID_KEYS = {"run_id", "order_id", "id"}

BEARER_TOKEN_RE = re.compile(r"\b(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
AUTH_HEADER_RE = re.compile(
    r"\b(?P<name>authorization|proxy-authorization|x-api-key|api-key|x-auth-token)"
    r"(?P<sep>\s*[:=]\s*)"
    r"(?P<value>[^\s,;]+)",
    re.IGNORECASE,
)
SECRET_ASSIGNMENT_RE = re.compile(
    r"\b(?P<name>[A-Z0-9_.-]*(?:API[_-]?KEY|API[_-]?SECRET|SECRET[_-]?KEY|TOKEN|PASSWORD|AUTH)[A-Z0-9_.-]*)"
    r"(?P<sep>\s*[:=]\s*)"
    r"(?P<quote>[\"']?)"
    r"(?P<value>[^\s,;`\"']+)"
    r"(?P=quote)",
    re.IGNORECASE,
)
SECRET_VALUE_RE = re.compile(
    r"\b("
    r"sk-[A-Za-z0-9_-]{20,}|"
    r"pk_test_[A-Za-z0-9_-]{20,}|"
    r"AKIA[A-Z0-9]{16}|"
    r"xox[baprs]-[A-Za-z0-9_-]{10,}|"
    r"ghp_[A-Za-z0-9]{36}|"
    r"pplx-[A-Za-z0-9_-]{20,}|"
    r"AIza[0-9A-Za-z_-]{20,}"
    r")\b",
    re.IGNORECASE,
)
CANDIDATE_TOKEN_RE = re.compile(r"[A-Za-z0-9._~+/=-]{28,160}")
SECRET_NAME_RE = re.compile(
    r"^(?:export\s+)?"
    r"(?P<name>[A-Z0-9_]*(?:API_KEY|API_SECRET|SECRET_KEY|TOKEN|PASSWORD)[A-Z0-9_]*)"
    r"\s*=\s*(?P<value>.*)$"
)


class RedactionEngine:
    def __init__(self) -> None:
        self._known_secrets: set[str] = set()
        self.refresh()

    def refresh(self) -> None:
        self._known_secrets = {
            value
            for key, value in os.environ.items()
            if is_secret_key(key) and value and len(value) >= 4
        }

    @property
    def known_secrets(self) -> set[str]:
        return set(self._known_secrets)

    def redact_text(self, text: str, *, key_context: str | None = None) -> str:
        if not isinstance(text, str):
            return text

        redacted = text
        for secret in sorted(self._known_secrets, key=len, reverse=True):
            redacted = redacted.replace(secret, REDACTED_VALUE)

        redacted = BEARER_TOKEN_RE.sub(r"\1[REDACTED]", redacted)
        redacted = AUTH_HEADER_RE.sub(r"\g<name>\g<sep>[REDACTED]", redacted)
        redacted = SECRET_ASSIGNMENT_RE.sub(self._secret_assignment_sub, redacted)
        redacted = SECRET_VALUE_RE.sub(REDACTED_VALUE, redacted)
        if (key_context or "").lower() not in SAFE_ID_KEYS:
            redacted = self._redact_high_entropy_substrings(redacted)
        if _scan_text_for_secrets(redacted):
            redacted = SECRET_ASSIGNMENT_RE.sub(self._secret_assignment_sub, redacted)
        return redacted

    def redact_payload(self, payload: Any, *, key_context: str | None = None) -> Any:
        if isinstance(payload, BaseModel):
            payload = payload.model_dump(mode="python")
        if is_dataclass(payload):
            payload = asdict(payload)
        if isinstance(payload, dict):
            redacted: dict[Any, Any] = {}
            for key, value in payload.items():
                key_text = str(key)
                if self._is_sensitive_key(key_text):
                    redacted[key] = REDACTED_VALUE
                else:
                    redacted[key] = self.redact_payload(value, key_context=key_text)
            return redacted
        if isinstance(payload, list | tuple):
            return [self.redact_payload(item, key_context=key_context) for item in payload]
        if isinstance(payload, datetime | date):
            return payload.isoformat()
        if isinstance(payload, str):
            return self.redact_text(payload, key_context=key_context)
        return payload

    def _is_sensitive_key(self, key: str) -> bool:
        key_upper = key.upper()
        if key_upper in SECRET_FIELD_NAMES:
            return True
        if is_secret_key(key):
            return True
        return any(marker in key_upper for marker in SECRET_MARKERS)

    def _secret_assignment_sub(self, match: re.Match[str]) -> str:
        key_name = match.group("name")
        if not self._is_sensitive_key(key_name):
            return match.group(0)
        quote = match.group("quote")
        return f"{key_name}{match.group('sep')}{quote}{REDACTED_VALUE}{quote}"

    def _looks_high_entropy_token(self, value: str) -> bool:
        token = value.strip()
        if len(token) < 28 or len(token) > 160:
            return False
        if any(ch.isspace() for ch in token):
            return False
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._~+/=-")
        if any(ch not in allowed for ch in token):
            return False
        has_alpha = any(ch.isalpha() for ch in token)
        has_digit = any(ch.isdigit() for ch in token)
        if not (has_alpha and has_digit):
            return False
        unique_ratio = len(set(token)) / len(token)
        return unique_ratio >= 0.45

    def _redact_high_entropy_substrings(self, text: str) -> str:
        def _sub(match: re.Match[str]) -> str:
            token = match.group(0)
            if self._looks_high_entropy_token(token):
                return REDACTED_VALUE
            return token

        return CANDIDATE_TOKEN_RE.sub(_sub, text)


_DEFAULT_ENGINE = RedactionEngine()


def default_redaction_engine() -> RedactionEngine:
    return _DEFAULT_ENGINE


def refresh_redaction_secrets() -> None:
    _DEFAULT_ENGINE.refresh()


def redact_text(text: str) -> str:
    return _DEFAULT_ENGINE.redact_text(text)


def redact_payload(payload: Any) -> Any:
    return _DEFAULT_ENGINE.redact_payload(payload)


def _scan_text_for_secrets(text: str) -> list[str]:
    findings: list[str] = []
    for line in text.splitlines():
        match = SECRET_NAME_RE.match(line.strip())
        if not match:
            continue
        value = match.group("value").strip().strip('"').strip("'")
        if value:
            findings.append(match.group("name"))
    return findings
