# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    brokers/errors.py
# PURPOSE: Converts broker exceptions into a safe, structured error. Broker SDKs
#          routinely put API keys, auth headers and full request bodies into their
#          exception text — and that text would otherwise land in the audit log.
# DEPS:    brokers.base (BrokerConfigurationError)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.error import URLError

from atlas_agent.brokers.base import BrokerConfigurationError


# --- CONFIGURATIONS & CONSTANTS ---

BROKER_ERROR_CODE_CONFIG = "broker_config_error"
BROKER_ERROR_CODE_TRANSPORT = "broker_transport_error"
BROKER_ERROR_CODE_DEPENDENCY = "broker_dependency_missing"
BROKER_ERROR_CODE_OPERATION = "broker_operation_failed"

_KNOWN_BROKER_NAMES = ("paper", "alpaca", "binance", "ccxt", "ibkr")


# ==============================================================================
# ERROR MODEL
# ==============================================================================

@dataclass(frozen=True)
class BrokerError:
    code: str
    operation: str
    broker: str
    # A CONSTANT drawn from _classify_exception() — never text derived from the
    # original exception. That is the containment boundary this module exists for.
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    def to_error_string(self) -> str:
        return f"{self.operation} failed [{self.code}]: {self.message}"


# ==============================================================================
# CLASSIFICATION
# ==============================================================================

def infer_broker_name(target: object | str | None) -> str:
    # Matched against a known list first, so the name in the audit trail is stable
    # regardless of which class or string the caller happened to pass.
    if target is None:
        return "unknown"
    raw = target if isinstance(target, str) else type(target).__name__
    lowered = str(raw).strip().lower()
    for candidate in _KNOWN_BROKER_NAMES:
        if candidate in lowered:
            return candidate
    # Unrecognised names are stripped to a safe character set rather than passed
    # through: this value is written to logs, and an arbitrary object's repr could
    # carry anything, including a connection string.
    sanitized = "".join(ch for ch in lowered if ch.isalnum() or ch in {"_", "-", "."})
    return sanitized or "unknown"


def make_broker_error(
    *,
    operation: str,
    broker: object | str | None,
    exc: Exception,
) -> BrokerError:
    code, message = _classify_exception(exc)
    return BrokerError(
        code=code,
        operation=operation,
        broker=infer_broker_name(broker),
        message=message,
    )


def _classify_exception(exc: Exception) -> tuple[str, str]:
    # The exception is used ONLY to select a bucket. Its text is never read, never
    # interpolated, never re-raised — every branch returns a hardcoded message.
    # Losing the detail is the price of never leaking a credential into a log line;
    # the code + operation pair is what makes the failure actionable instead.
    if isinstance(exc, BrokerConfigurationError):
        return (
            BROKER_ERROR_CODE_CONFIG,
            "broker configuration is invalid or incomplete",
        )
    if isinstance(exc, ModuleNotFoundError):
        return (
            BROKER_ERROR_CODE_DEPENDENCY,
            "required broker dependency is unavailable",
        )
    if isinstance(exc, (TimeoutError, ConnectionError, OSError, URLError)):
        return (
            BROKER_ERROR_CODE_TRANSPORT,
            "broker transport request failed",
        )
    return (
        BROKER_ERROR_CODE_OPERATION,
        "broker operation failed",
    )
