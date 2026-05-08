from __future__ import annotations

from dataclasses import asdict, is_dataclass
import functools
import inspect
import re
from typing import Any, Callable, TypeVar, cast


F = TypeVar("F", bound=Callable[..., Any])

SENSITIVE_KEY_MARKERS = (
    "API_KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "AUTH",
    "CREDENTIAL",
    "PRIVATE_KEY",
    "BOT_TOKEN",
)
USD_SENSITIVE_KEY_MARKERS = (
    "USD",
    "NOTIONAL",
    "POSITION_SIZE",
    "ACCOUNT_VALUE",
    "EQUITY",
    "BUYING_POWER",
    "BALANCE",
    "CASH",
)
PERCENT_KEY_MARKERS = ("PCT", "PERCENT", "PERCENTAGE", "RATIO")
SAFE_ID_KEYS = {"run_id", "order_id", "id", "symbol", "ticker"}

SECRET_ASSIGNMENT_RE = re.compile(
    r"\b(?P<name>[A-Z0-9_.-]*(?:API[_-]?KEY|API[_-]?SECRET|SECRET[_-]?KEY|TOKEN|PASSWORD|AUTH)[A-Z0-9_.-]*)"
    r"(?P<sep>\s*[:=]\s*)"
    r"(?P<quote>[\"']?)"
    r"(?P<value>[^\s,;`\"']+)"
    r"(?P=quote)",
    re.IGNORECASE,
)
BEARER_RE = re.compile(r"\b(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
AUTH_HEADER_RE = re.compile(
    r"\b(?P<name>authorization|proxy-authorization|x-api-key|api-key|x-auth-token)"
    r"(?P<sep>\s*[:=]\s*)"
    r"(?P<value>[^\s,;]+)",
    re.IGNORECASE,
)
SECRET_VALUE_RE = re.compile(
    r"\b("
    r"sk-[A-Za-z0-9_-]{20,}|"
    r"pplx-[A-Za-z0-9_-]{20,}|"
    r"AKIA[A-Z0-9]{16}|"
    r"xox[baprs]-[A-Za-z0-9_-]{10,}|"
    r"ghp_[A-Za-z0-9]{20,}|"
    r"AIza[0-9A-Za-z_-]{20,}"
    r")\b",
    re.IGNORECASE,
)
CANDIDATE_TOKEN_RE = re.compile(r"[A-Za-z0-9._~+/=-]{28,200}")
USD_AMOUNT_RE = re.compile(
    r"(?i)(?:\bUSD\s*[:=]?\s*\$?\s*\d[\d,]*(?:\.\d+)?\b|"
    r"\$\s*\d[\d,]*(?:\.\d+)?\b|"
    r"\b\d[\d,]*(?:\.\d+)?\s*USD\b)"
)
ACCOUNT_CONTEXT_NUMBER_RE = re.compile(
    r"(?i)\b(?P<label>account|acct|iban)\s*[:#-]?\s*(?P<number>\d{6,20})\b"
)
LONG_DIGIT_RE = re.compile(r"\b\d{8,20}\b")


def safe_output(func: F) -> F:
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
            result = await func(*args, **kwargs)
            return sanitize_output(result)

        return cast(F, _async_wrapper)

    @functools.wraps(func)
    def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        result = func(*args, **kwargs)
        return sanitize_output(result)

    return cast(F, _sync_wrapper)


def sanitize_output(value: Any, *, key_context: str | None = None) -> Any:
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            key_upper = key.upper()
            if _is_sensitive_key(key_upper):
                redacted[key] = "[REDACTED]"
                continue
            if _is_usd_sensitive_key(key_upper) and not _is_percent_key(key_upper):
                redacted[key] = _sanitize_usd_value(item)
                continue
            redacted[key] = sanitize_output(item, key_context=key)
        return redacted
    if isinstance(value, list):
        return [sanitize_output(item, key_context=key_context) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_output(item, key_context=key_context) for item in value)
    if isinstance(value, str):
        return _sanitize_string(value, key_context=key_context)
    return value


def _is_sensitive_key(key_upper: str) -> bool:
    return any(marker in key_upper for marker in SENSITIVE_KEY_MARKERS)


def _is_usd_sensitive_key(key_upper: str) -> bool:
    return any(marker in key_upper for marker in USD_SENSITIVE_KEY_MARKERS)


def _is_percent_key(key_upper: str) -> bool:
    return any(marker in key_upper for marker in PERCENT_KEY_MARKERS)


def _sanitize_usd_value(value: Any) -> Any:
    if isinstance(value, (int, float)):
        return "[REDACTED_USD]"
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return stripped
        return "USD [REDACTED]"
    if isinstance(value, list):
        return [_sanitize_usd_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_usd_value(item) for item in value)
    if isinstance(value, dict):
        return {str(key): _sanitize_usd_value(item) for key, item in value.items()}
    return "[REDACTED_USD]"


def _sanitize_string(value: str, *, key_context: str | None) -> str:
    text = value
    text = BEARER_RE.sub(r"\1[REDACTED]", text)
    text = AUTH_HEADER_RE.sub(r"\g<name>\g<sep>[REDACTED]", text)
    text = SECRET_ASSIGNMENT_RE.sub(_secret_assignment_sub, text)
    text = SECRET_VALUE_RE.sub("[REDACTED]", text)
    text = ACCOUNT_CONTEXT_NUMBER_RE.sub(_account_context_sub, text)
    if (key_context or "").lower() not in SAFE_ID_KEYS:
        text = LONG_DIGIT_RE.sub("[REDACTED_ACCOUNT]", text)
        text = CANDIDATE_TOKEN_RE.sub(_token_sub, text)
    text = USD_AMOUNT_RE.sub("USD [REDACTED]", text)
    return text


def _secret_assignment_sub(match: re.Match[str]) -> str:
    key_name = match.group("name")
    if not _is_sensitive_key(key_name.upper()):
        return match.group(0)
    quote = match.group("quote")
    return f"{key_name}{match.group('sep')}{quote}[REDACTED]{quote}"


def _account_context_sub(match: re.Match[str]) -> str:
    label = match.group("label")
    number = match.group("number")
    suffix = number[-4:] if len(number) >= 4 else "****"
    return f"{label}: ****{suffix}"


def _token_sub(match: re.Match[str]) -> str:
    token = match.group(0)
    if _looks_high_entropy(token):
        return "[REDACTED]"
    return token


def _looks_high_entropy(token: str) -> bool:
    if len(token) < 28 or len(token) > 200:
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

