# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    runtime_errors.py
# PURPOSE: Turns arbitrary exceptions into a sanitised, structured error shape.
#          The point is containment: exception text from brokers and LLM providers
#          routinely carries API keys and request bodies, and must never reach a
#          log line, a CLI envelope or a Telegram message.
# DEPS:    stdlib only (dataclasses)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from dataclasses import dataclass, asdict


# ==============================================================================
# SAFE ERROR MODEL
# ==============================================================================

@dataclass(frozen=True)
class SafeRuntimeError:
    code: str
    operation: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


# ==============================================================================
# EXCEPTION SANITISATION
# ==============================================================================

def make_safe_runtime_error(*, operation: str, exc: Exception) -> SafeRuntimeError:
    """Convert any runtime exception into a safe structured error.

    Raw exception text is never forwarded into the returned message.
    """
    # Every branch maps to a *constant* message. Interpolating `exc` here — even
    # "just the type" — is how secrets leak, so the exception is used only to pick
    # a bucket, never as a source of text.
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        code = "transport_error"
        message = "transport request failed"
    elif isinstance(exc, ValueError):
        code = "validation_error"
        message = "input validation failed"
    else:
        code = "operation_failed"
        message = "operation failed"
    return SafeRuntimeError(code=code, operation=operation, message=message)
