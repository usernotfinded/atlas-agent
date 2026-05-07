from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from atlas_agent.events.schema import validate_event_record
from atlas_agent.safety.secrets import scan_text_for_secrets


SECRET_MARKERS = ("API_KEY", "SECRET", "TOKEN", "PASSWORD", "AUTH", "KEY")
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
SAFE_ID_KEYS = {"run_id", "order_id", "id"}


def generate_run_id() -> str:
    return uuid4().hex


class EventLogger:
    def __init__(self, events_dir: str | Path = "events") -> None:
        self.events_dir = Path(events_dir)
        self.events_dir.mkdir(parents=True, exist_ok=True)

    def path_for_day(self, day: date | None = None) -> Path:
        effective_day = day or datetime.now(UTC).date()
        return self.events_dir / f"{effective_day.isoformat()}.jsonl"

    def write(
        self,
        event_type: str,
        *,
        run_id: str,
        command: str,
        mode: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        record = {
            "timestamp": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "event_type": event_type,
            "run_id": run_id,
            "command": command,
            "mode": mode,
            "payload": _redact(payload or {}),
        }
        # Final pass immediately before writing any event record.
        record = _redact(record)
        errors = validate_event_record(record)
        if errors:
            raise ValueError(f"invalid event record: {', '.join(errors)}")
        with self.path_for_day().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def list_event_files(events_dir: str | Path = "events") -> list[Path]:
    base = Path(events_dir)
    if not base.exists():
        return []
    return sorted(path for path in base.glob("*.jsonl") if path.is_file())


def read_event_file(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    events: list[dict[str, Any]] = []
    for line_no, raw_line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{target}:{line_no}: invalid JSON: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"{target}:{line_no}: event must be a JSON object")
        events.append(parsed)
    return events


def read_recent_events(events_dir: str | Path = "events", *, limit: int = 50) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    all_events: list[dict[str, Any]] = []
    for path in reversed(list_event_files(events_dir)):
        events = read_event_file(path)
        all_events[0:0] = events
        if len(all_events) >= limit:
            break
    if len(all_events) > limit:
        return all_events[-limit:]
    return all_events


def latest_event_file(events_dir: str | Path = "events") -> Path | None:
    files = list_event_files(events_dir)
    if not files:
        return None
    return files[-1]


def _redact(value: Any, *, key_context: str | None = None) -> Any:
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_key(key_text):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact(item, key_context=key_text)
        return redacted
    if isinstance(value, list | tuple):
        return [_redact(item, key_context=key_context) for item in value]
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, str):
        return _redact_string(value, key_context=key_context)
    return value


def _is_sensitive_key(key: str) -> bool:
    key_upper = key.upper()
    if key_upper in SECRET_FIELD_NAMES:
        return True
    return any(marker in key_upper for marker in SECRET_MARKERS)


def _redact_string(value: str, *, key_context: str | None = None) -> str:
    text = value
    text = BEARER_TOKEN_RE.sub(r"\1[REDACTED]", text)
    text = AUTH_HEADER_RE.sub(r"\g<name>\g<sep>[REDACTED]", text)
    text = SECRET_ASSIGNMENT_RE.sub(_secret_assignment_sub, text)
    text = SECRET_VALUE_RE.sub("[REDACTED]", text)
    if (key_context or "").lower() not in SAFE_ID_KEYS:
        text = _redact_high_entropy_substrings(text)
    if scan_text_for_secrets(text):
        return SECRET_ASSIGNMENT_RE.sub(_secret_assignment_sub, text)
    return text


def _secret_assignment_sub(match: re.Match[str]) -> str:
    key_name = match.group("name")
    if not _is_sensitive_key(key_name):
        return match.group(0)
    quote = match.group("quote")
    return f"{key_name}{match.group('sep')}{quote}[REDACTED]{quote}"


def _looks_high_entropy_token(value: str) -> bool:
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


def _redact_high_entropy_substrings(text: str) -> str:
    def _sub(match: re.Match[str]) -> str:
        token = match.group(0)
        if _looks_high_entropy_token(token):
            return "[REDACTED]"
        return token

    return CANDIDATE_TOKEN_RE.sub(_sub, text)
