from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TradingQualityThresholdPolicy:
    """Conservative, configurable thresholds for the trading-quality gate.

    Defaults are chosen for tests/demo and do not require profitability.
    """

    min_bars_processed: int = 10
    min_fills: int = 1
    min_no_trade_decisions: int = 1
    min_risk_rejections: int = 1
    max_drawdown_pct: float = 50.0
    max_exposure_pct: float = 200.0
    max_turnover: float = 100.0
    max_cost_impact_pct: float = 10.0
    min_data_coverage: float = 0.5
    max_invalid_metric_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_bars_processed": self.min_bars_processed,
            "min_fills": self.min_fills,
            "min_no_trade_decisions": self.min_no_trade_decisions,
            "min_risk_rejections": self.min_risk_rejections,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_exposure_pct": self.max_exposure_pct,
            "max_turnover": self.max_turnover,
            "max_cost_impact_pct": self.max_cost_impact_pct,
            "min_data_coverage": self.min_data_coverage,
            "max_invalid_metric_count": self.max_invalid_metric_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TradingQualityThresholdPolicy:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})
