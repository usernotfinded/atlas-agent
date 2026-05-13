from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.error import URLError

from atlas_agent.brokers.base import BrokerConfigurationError


BROKER_ERROR_CODE_CONFIG = "broker_config_error"
BROKER_ERROR_CODE_TRANSPORT = "broker_transport_error"
BROKER_ERROR_CODE_DEPENDENCY = "broker_dependency_missing"
BROKER_ERROR_CODE_OPERATION = "broker_operation_failed"

_KNOWN_BROKER_NAMES = ("paper", "alpaca", "binance", "ccxt", "ibkr")


@dataclass(frozen=True)
class BrokerError:
    code: str
    operation: str
    broker: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    def to_error_string(self) -> str:
        return f"{self.operation} failed [{self.code}]: {self.message}"


def infer_broker_name(target: object | str | None) -> str:
    if target is None:
        return "unknown"
    raw = target if isinstance(target, str) else type(target).__name__
    lowered = str(raw).strip().lower()
    for candidate in _KNOWN_BROKER_NAMES:
        if candidate in lowered:
            return candidate
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
