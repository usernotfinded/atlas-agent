from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class SafeRuntimeError:
    code: str
    operation: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def make_safe_runtime_error(*, operation: str, exc: Exception) -> SafeRuntimeError:
    """Convert any runtime exception into a safe structured error.

    Raw exception text is never forwarded into the returned message.
    """
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
