from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class ResearchReport:
    symbol: str
    provider: str
    summary: str
    citations: tuple[str, ...] = ()
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
