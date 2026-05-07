from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reasons: tuple[str, ...] = ()

