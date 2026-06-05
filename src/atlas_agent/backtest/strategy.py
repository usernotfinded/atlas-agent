from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, Sequence

from pydantic import BaseModel, Field

from atlas_agent.backtest.models import BacktestConfig, BacktestOrder, BacktestPosition, MarketBar


class StrategyParameterSpec(BaseModel):
    type: Literal["int", "float", "bool", "str"]
    description: str
    default: Any = None
    required: bool = False
    min_value: float | None = None
    max_value: float | None = None
    choices: list[Any] = Field(default_factory=list)


class StrategyParameterValidationError(ValueError):
    pass


class StrategyMetadata(BaseModel):
    strategy_id: str
    name: str
    description: str
    version: str = "1.0"
    parameters: dict[str, StrategyParameterSpec] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class StrategyValidationIssue(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    message: str


class StrategyValidationResult(BaseModel):
    strategy_id: str
    status: Literal["valid", "invalid"]
    issues: list[StrategyValidationIssue] = Field(default_factory=list)
    metadata: StrategyMetadata | None = None


@dataclass(frozen=True)
class StrategyContext:
    run_id: str
    symbol: str
    bar_index: int
    cash: float
    positions: dict[str, BacktestPosition]
    pending_orders: list[BacktestOrder]
    config: BacktestConfig


class BacktestStrategy(Protocol):
    metadata: StrategyMetadata

    def generate_orders(
        self,
        *,
        bars: Sequence[MarketBar],
        context: StrategyContext,
    ) -> list[BacktestOrder]:
        ...


def coerce_strategy_parameters(
    metadata: StrategyMetadata,
    provided: dict[str, Any] | None,
) -> dict[str, Any]:
    provided = provided or {}
    unknown = sorted(set(provided) - set(metadata.parameters))
    if unknown:
        joined = ", ".join(unknown)
        raise StrategyParameterValidationError(
            f"Unknown parameter(s) for {metadata.strategy_id}: {joined}"
        )

    coerced: dict[str, Any] = {}
    for name, spec in metadata.parameters.items():
        if name in provided:
            value = _coerce_value(name, provided[name], spec)
        elif spec.required:
            raise StrategyParameterValidationError(
                f"Missing required parameter for {metadata.strategy_id}: {name}"
            )
        else:
            value = spec.default
        _validate_range(name, value, spec)
        coerced[name] = value
    return coerced


def _coerce_value(name: str, value: Any, spec: StrategyParameterSpec) -> Any:
    try:
        if spec.type == "bool":
            if isinstance(value, bool):
                coerced = value
            elif isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in {"1", "true", "t", "yes", "y", "on"}:
                    coerced = True
                elif normalized in {"0", "false", "f", "no", "n", "off"}:
                    coerced = False
                else:
                    raise ValueError
            else:
                raise ValueError
        elif spec.type == "int":
            if isinstance(value, bool):
                raise ValueError
            coerced = int(value)
        elif spec.type == "float":
            if isinstance(value, bool):
                raise ValueError
            coerced = float(value)
        else:
            coerced = str(value)
    except (TypeError, ValueError) as exc:
        raise StrategyParameterValidationError(
            f"Parameter {name} must be {spec.type}"
        ) from exc

    if spec.choices and coerced not in spec.choices:
        raise StrategyParameterValidationError(
            f"Parameter {name} must be one of: {', '.join(str(item) for item in spec.choices)}"
        )
    return coerced


def _validate_range(name: str, value: Any, spec: StrategyParameterSpec) -> None:
    if spec.type not in {"int", "float"}:
        return
    numeric = float(value)
    if spec.min_value is not None and numeric < spec.min_value:
        raise StrategyParameterValidationError(
            f"Parameter {name} must be >= {spec.min_value:g}"
        )
    if spec.max_value is not None and numeric > spec.max_value:
        raise StrategyParameterValidationError(
            f"Parameter {name} must be <= {spec.max_value:g}"
        )
