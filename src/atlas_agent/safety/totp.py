from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time
from datetime import datetime


DEFAULT_INTERVAL_SECONDS = 30
DEFAULT_DIGITS = 6


def verify_totp(
    secret: str,
    code: str,
    *,
    for_time: datetime | None = None,
    valid_window: int = 1,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    digits: int = DEFAULT_DIGITS,
) -> bool:
    normalized = _normalize_code(code, digits=digits)
    if normalized is None:
        return False
    counter_now = _counter(for_time=for_time, interval_seconds=interval_seconds)
    for offset in range(-valid_window, valid_window + 1):
        if _totp_at_counter(secret, counter_now + offset, digits=digits) == normalized:
            return True
    return False


def generate_totp(
    secret: str,
    *,
    for_time: datetime | None = None,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    digits: int = DEFAULT_DIGITS,
) -> str:
    counter_now = _counter(for_time=for_time, interval_seconds=interval_seconds)
    return _totp_at_counter(secret, counter_now, digits=digits)


def _counter(*, for_time: datetime | None, interval_seconds: int) -> int:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    if for_time is None:
        epoch_seconds = int(time.time())
    else:
        epoch_seconds = int(for_time.timestamp())
    return epoch_seconds // interval_seconds


def _totp_at_counter(secret: str, counter: int, *, digits: int) -> str:
    key = _decode_secret(secret)
    counter_bytes = struct.pack(">Q", max(counter, 0))
    digest = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    mod = 10**digits
    code = binary % mod
    return f"{code:0{digits}d}"


def _decode_secret(secret: str) -> bytes:
    cleaned = "".join(secret.strip().split()).upper()
    if not cleaned:
        raise ValueError("empty TOTP secret")
    padding = "=" * ((8 - (len(cleaned) % 8)) % 8)
    return base64.b32decode(cleaned + padding, casefold=True)


def _normalize_code(code: str, *, digits: int) -> str | None:
    cleaned = "".join(ch for ch in code.strip() if ch.isdigit())
    if len(cleaned) != digits:
        return None
    return cleaned
