# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    safety/totp.py
# PURPOSE: RFC 6238 TOTP, implemented on stdlib primitives. This is the second
#          factor guarding the one irreversible-in-the-wrong-direction action in
#          the system: resuming the agent after a kill switch.
# DEPS:    stdlib only (hmac, hashlib, base64, struct) — no third-party OTP lib,
#          so the credential path pulls in no extra supply-chain surface.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time
from datetime import datetime


# --- CONFIGURATIONS & CONSTANTS ---

# The RFC 6238 defaults, which is what every authenticator app assumes.
DEFAULT_INTERVAL_SECONDS = 30
DEFAULT_DIGITS = 6


# ==============================================================================
# PUBLIC API
# ==============================================================================

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
    # valid_window=1 accepts the neighbouring steps as well as the current one,
    # tolerating clock skew between the phone and this machine. Widening it trades
    # security for convenience linearly — each extra step is another 30s during
    # which an observed code stays replayable.
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


# ==============================================================================
# RFC 6238 INTERNALS
# ==============================================================================

def _counter(*, for_time: datetime | None, interval_seconds: int) -> int:
    # The TOTP counter is just Unix time bucketed into `interval_seconds` windows.
    # `for_time` exists so tests can pin the clock — never pass it in production.
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
    # SHA-1 is mandated by RFC 6238 and is what authenticator apps implement. Its
    # collision weakness is irrelevant here: this is HMAC, which relies on the
    # PRF property, not collision resistance.
    digest = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    # Dynamic truncation (RFC 4226 §5.3): the low nibble of the last byte selects
    # which 4 bytes of the digest to read, so the code depends on the whole digest
    # rather than a fixed slice of it.
    offset = digest[-1] & 0x0F
    # Masking the top bit sidesteps signed/unsigned ambiguity across implementations.
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    mod = 10**digits
    code = binary % mod
    # Zero-padded: a code of 000042 must not compare as "42".
    return f"{code:0{digits}d}"


def _decode_secret(secret: str) -> bytes:
    # Authenticator apps hand out base32 in spaced, lower/upper-case groups. Strip
    # the whitespace and restore the padding the user's copy-paste dropped, so a
    # correctly-typed secret is not rejected on formatting grounds.
    cleaned = "".join(secret.strip().split()).upper()
    if not cleaned:
        raise ValueError("empty TOTP secret")
    padding = "=" * ((8 - (len(cleaned) % 8)) % 8)
    return base64.b32decode(cleaned + padding, casefold=True)


def _normalize_code(code: str, *, digits: int) -> str | None:
    # Drops spaces and dashes people type, then insists on an exact digit count:
    # a short or long code is malformed, and comparing it would be pointless work.
    cleaned = "".join(ch for ch in code.strip() if ch.isdigit())
    if len(cleaned) != digits:
        return None
    return cleaned
