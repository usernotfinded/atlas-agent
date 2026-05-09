from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _session_id() -> str:
    return f"sess_{uuid4().hex[:12]}"


def _started_at() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class Session(BaseModel):
    id: str = Field(default_factory=_session_id)
    started_at: str = Field(default_factory=_started_at)
    trigger: str = "manual"
    turn_count: int = 0
    trust_mode: str = "manual"
    context_snapshot: dict[str, Any] = Field(default_factory=dict)
    has_summarized: bool = False
